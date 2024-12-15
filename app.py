from flask import Flask, render_template, request, jsonify
import requests
from datetime import datetime, timedelta
import concurrent.futures
from urllib.parse import quote
import json
import time

app = Flask(__name__)

# Cache para armazenar dados frequentemente acessados
CACHE = {
    'partidos': None,
    'estados': None,
    'tipos_discurso': [
        "Sessão Deliberativa",
        "Sessão Não Deliberativa",
        "Sessão Solene",
        "Reunião Deliberativa",
        "Reunião de Debate",
        "Reunião Técnica",
        "Audiência Pública",
        "Comissão Geral",
        "Seminário"
    ],
    'cache_time': None
}

# Add this at the top with other constants
PARTIDOS_ATIVOS = [
    {'sigla': 'AVANTE'},
    {'sigla': 'CIDADANIA'},
    {'sigla': 'DC'},
    {'sigla': 'MDB'},
    {'sigla': 'NOVO'},
    {'sigla': 'PATRIOTA'},
    {'sigla': 'PCdoB'},
    {'sigla': 'PL'},
    {'sigla': 'PODE'},
    {'sigla': 'PP'},
    {'sigla': 'PROS'},
    {'sigla': 'PSB'},
    {'sigla': 'PSD'},
    {'sigla': 'PSDB'},
    {'sigla': 'PSol'},
    {'sigla': 'PT'},
    {'sigla': 'PTB'},
    {'sigla': 'PV'},
    {'sigla': 'REPUBLICANOS'},
    {'sigla': 'SOLIDARIEDADE'},
    {'sigla': 'UNIÃO'}
]

# Update the timeout configuration at the top
REQUESTS_TIMEOUT = 10
MAX_RETRIES = 1

# Add this new function for making resilient requests
def make_resilient_request(url, params=None, timeout=REQUESTS_TIMEOUT):
    """Make HTTP request with retry logic"""
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(
                url, 
                params=params, 
                timeout=timeout,
                headers={'User-Agent': 'Mozilla/5.0'}  # Add User-Agent header
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            if attempt == MAX_RETRIES - 1:  # Last attempt
                print(f"Error after {MAX_RETRIES} attempts for {url}: {e}")
                raise
            print(f"Attempt {attempt + 1} failed for {url}: {e}")
            time.sleep(1)  # Wait before retrying

def atualizar_cache():
    """Atualiza o cache de dados básicos se necessário"""
    agora = datetime.now()
    
    # Always use PARTIDOS_ATIVOS for now to avoid API calls
    CACHE['partidos'] = PARTIDOS_ATIVOS
    CACHE['cache_time'] = agora
    
    # No need to make API calls that might timeout
    return

def get_deputados(filtros=None):
    """Busca lista de deputados com filtros"""
    # Add caching for deputados
    cache_key = f"deputados_{filtros.get('partido', '')}_{filtros.get('estado', '')}"
    if cache_key in CACHE and CACHE[cache_key]['time'] > datetime.now() - timedelta(hours=1):
        return CACHE[cache_key]['data']

    url = "https://dadosabertos.camara.leg.br/api/v2/deputados"
    params = {
        'ordem': 'ASC',
        'ordenarPor': 'nome',
        'itens': 20  # Limit items to 20
    }
    
    if filtros:
        if filtros.get('partido'):
            params['siglaPartido'] = filtros['partido']
        if filtros.get('estado'):
            params['siglaUf'] = filtros['estado']
            
    try:
        data = make_resilient_request(url, params=params)
        CACHE[cache_key] = {
            'data': data['dados'],
            'time': datetime.now()
        }
        return data['dados']
    except Exception as e:
        print(f"Erro ao buscar deputados: {e}")
        return []

def classificar_tipo_evento(tipo_evento):
    """Classifica o tipo de evento em uma categoria padronizada"""
    tipo_lower = tipo_evento.lower() if tipo_evento else ''
    
    if 'sessão deliberativa' in tipo_lower:
        return 'Sessão Deliberativa'
    elif 'sessão não deliberativa' in tipo_lower:
        return 'Sessão Não Deliberativa'
    elif 'sessão solene' in tipo_lower:
        return 'Sessão Solene'
    elif 'reunião deliberativa' in tipo_lower:
        return 'Reunião Deliberativa'
    elif 'reunião de debate' in tipo_lower:
        return 'Reunião de Debate'
    elif 'reunião técnica' in tipo_lower:
        return 'Reunião Técnica'
    elif 'audiência pública' in tipo_lower:
        return 'Audiência Pública'
    elif 'comissão geral' in tipo_lower:
        return 'Comissão Geral'
    elif 'seminário' in tipo_lower:
        return 'Seminário'
    else:
        return tipo_evento if tipo_evento else 'Outro'

def buscar_discursos_deputado(id_deputado, filtros):
    """Simplified version to only get speeches from a specific deputy"""
    url = f"https://dadosabertos.camara.leg.br/api/v2/deputados/{id_deputado}/discursos"
    
    params = {
        'dataInicio': filtros['data_inicio'],
        'dataFim': filtros['data_fim'],
        'ordenarPor': 'dataHoraInicio',
        'ordem': 'DESC',
        'itens': 20  # Limit to 20 most recent speeches
    }
    
    try:
        # Get deputy info first
        url_deputado = f"https://dadosabertos.camara.leg.br/api/v2/deputados/{id_deputado}"
        dep_response = requests.get(url_deputado, timeout=REQUESTS_TIMEOUT)
        dep_data = dep_response.json()['dados']
        
        info_deputado = {
            'nome': dep_data['ultimoStatus']['nomeEleitoral'],
            'partido': dep_data['ultimoStatus']['siglaPartido'],
            'estado': dep_data['ultimoStatus']['siglaUf'],
            'foto': dep_data['ultimoStatus']['urlFoto'],
            'id': id_deputado
        }
        
        # Then get speeches
        response = requests.get(url, params=params, timeout=REQUESTS_TIMEOUT)
        discursos = response.json()['dados']
        
        return [{
            **info_deputado,
            'data': discurso.get('dataHoraInicio', '').split('T')[0],
            'hora': discurso.get('dataHoraInicio', '').split('T')[1][:5] if 'T' in discurso.get('dataHoraInicio', '') else '',
            'sumario': discurso.get('transcricao', '')[:300] + '...',  # Shorter summary
            'transcricao_completa': discurso.get('transcricao', ''),
            'evento': classificar_tipo_evento(discurso.get('faseEvento', {}).get('titulo', '')),
            'id_discurso': discurso.get('id', '')
        } for discurso in discursos[:20]]  # Limit to 20 speeches
        
    except Exception as e:
        print(f"Erro ao buscar discursos do deputado {id_deputado}: {e}")
        return []

def aplicar_paginacao(resultados, pagina, itens_por_pagina):
    """Aplica paginação aos resultados"""
    inicio = (pagina - 1) * itens_por_pagina
    fim = inicio + itens_por_pagina
    return {
        'total': len(resultados),
        'discursos': resultados[inicio:fim]
    }

@app.route('/')
@app.route('/home')
def home():
    return render_template('discursos.html')



@app.route('/buscar')
def buscar():
    try:
        deputado_id = request.args.get('deputado_id', '')
        if not deputado_id:
            return jsonify({
                'total': 0,
                'discursos': [],
                'message': 'Por favor, selecione um deputado específico para buscar seus discursos.'
            })

        periodo = int(request.args.get('periodo', '30'))
        tipo = request.args.get('tipo', '')
        
        data_fim = datetime.now()
        data_inicio = data_fim - timedelta(days=periodo)
        
        filtros = {
            'tipo': tipo,
            'data_inicio': data_inicio.strftime('%Y-%m-%d'),
            'data_fim': data_fim.strftime('%Y-%m-%d')
        }
        
        discursos = buscar_discursos_deputado(deputado_id, filtros)
        
        if tipo:
            discursos = [d for d in discursos if d['evento'] == tipo]
            
        return jsonify({
            'total': len(discursos),
            'discursos': discursos
        })
        
    except Exception as e:
        print(f"Erro na busca: {e}")
        return jsonify({
            'total': 0,
            'discursos': [],
            'message': 'Houve um erro ao buscar os discursos. Por favor, tente novamente.'
        })

@app.route('/partidos')
def listar_partidos():
    atualizar_cache()
    # If cache is empty for some reason, use the fallback list
    if not CACHE['partidos']:
        CACHE['partidos'] = PARTIDOS_ATIVOS
    return jsonify(CACHE['partidos'])

@app.route('/estados')
def listar_estados():
    atualizar_cache()
    estados = [
        {"sigla": "AC", "nome": "Acre"},
        {"sigla": "AL", "nome": "Alagoas"},
        {"sigla": "AP", "nome": "Amapá"},
        {"sigla": "AM", "nome": "Amazonas"},
        {"sigla": "BA", "nome": "Bahia"},
        {"sigla": "CE", "nome": "Ceará"},
        {"sigla": "DF", "nome": "Distrito Federal"},
        {"sigla": "ES", "nome": "Espírito Santo"},
        {"sigla": "GO", "nome": "Goiás"},
        {"sigla": "MA", "nome": "Maranhão"},
        {"sigla": "MT", "nome": "Mato Grosso"},
        {"sigla": "MS", "nome": "Mato Grosso do Sul"},
        {"sigla": "MG", "nome": "Minas Gerais"},
        {"sigla": "PA", "nome": "Pará"},
        {"sigla": "PB", "nome": "Paraíba"},
        {"sigla": "PR", "nome": "Paraná"},
        {"sigla": "PE", "nome": "Pernambuco"},
        {"sigla": "PI", "nome": "Piauí"},
        {"sigla": "RJ", "nome": "Rio de Janeiro"},
        {"sigla": "RN", "nome": "Rio Grande do Norte"},
        {"sigla": "RS", "nome": "Rio Grande do Sul"},
        {"sigla": "RO", "nome": "Rondônia"},
        {"sigla": "RR", "nome": "Roraima"},
        {"sigla": "SC", "nome": "Santa Catarina"},
        {"sigla": "SP", "nome": "São Paulo"},
        {"sigla": "SE", "nome": "Sergipe"},
        {"sigla": "TO", "nome": "Tocantins"}
    ]
    CACHE['estados'] = estados
    return jsonify(estados)

@app.route('/tipos-discurso')
def listar_tipos_discurso():
    atualizar_cache()
    return jsonify(CACHE['tipos_discurso'])

@app.route('/discurso/<id_discurso>')
def ver_discurso(id_discurso):
    return render_template('discurso.html', discurso=None)

@app.route('/compartilhar/<id_discurso>')
def compartilhar_discurso(id_discurso):
    base_url = request.host_url.rstrip('/')
    url = f"{base_url}/discurso/{id_discurso}"
    return jsonify({
        'url': url,
        'twitter': f"https://twitter.com/intent/tweet?url={quote(url)}",
        'facebook': f"https://www.facebook.com/sharer/sharer.php?u={quote(url)}",
        'whatsapp': f"https://wa.me/?text={quote(url)}"
    })

@app.route('/deputados/buscar')
def buscar_deputados():
    """Busca deputados pelo nome"""
    termo = request.args.get('termo', '').lower()
    
    if not termo or len(termo) < 3:
        return jsonify([])
        
    try:
        # Busca todos os deputados
        url = "https://dadosabertos.camara.leg.br/api/v2/deputados"
        params = {
            'ordem': 'ASC',
            'ordenarPor': 'nome'
        }
        
        response = requests.get(url, params=params)
        deputados = response.json()['dados']
        
        # Filtra os deputados que correspondem ao termo de busca
        deputados_filtrados = [
            {
                'id': dep['id'],
                'nome': dep['nome'],
                'partido': dep['siglaPartido'],
                'estado': dep['siglaUf'],
                'foto': dep['urlFoto']
            }
            for dep in deputados
            if termo in dep['nome'].lower()
        ]
        
        # Limita a 10 resultados
        return jsonify(deputados_filtrados[:10])
        
    except Exception as e:
        print(f"Erro ao buscar deputados: {e}")
        return jsonify([])

if __name__ == "__main__":
    app.run(debug=True)
+ app = app