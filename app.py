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
REQUESTS_TIMEOUT = 15  # Reduce timeout to 15 seconds
MAX_WORKERS = 2  # Keep workers at 2
MAX_RETRIES = 2  # Reduce retries to 2

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
    url = "https://dadosabertos.camara.leg.br/api/v2/deputados"
    params = {
        'ordem': 'ASC',
        'ordenarPor': 'nome'
    }
    
    if filtros:
        if filtros.get('partido'):
            params['siglaPartido'] = filtros['partido']
        if filtros.get('estado'):
            params['siglaUf'] = filtros['estado']
            
    try:
        data = make_resilient_request(url, params=params)
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
    """Busca discursos de um deputado específico com filtros"""
    url = f"https://dadosabertos.camara.leg.br/api/v2/deputados/{id_deputado}/discursos"
    
    params = {
        'dataInicio': filtros['data_inicio'],
        'dataFim': filtros['data_fim'],
        'ordenarPor': 'dataHoraInicio',
        'ordem': 'DESC',
        'itens': 100
    }
    
    try:
        # Get deputy info
        url_deputado = f"https://dadosabertos.camara.leg.br/api/v2/deputados/{id_deputado}"
        dep_data = make_resilient_request(url_deputado)['dados']
        
        info_deputado = {
            'nome': dep_data['ultimoStatus']['nomeEleitoral'],
            'partido': dep_data['ultimoStatus']['siglaPartido'],
            'estado': dep_data['ultimoStatus']['siglaUf'],
            'foto': dep_data['ultimoStatus']['urlFoto'],
            'id': id_deputado
        }
        
        # Get speeches
        discursos_data = make_resilient_request(url, params=params)
        discursos = discursos_data['dados']
        
        discursos_filtrados = []
        for discurso in discursos:
            # Pega a fase do evento e classifica
            fase_evento = discurso.get('faseEvento', {}).get('titulo', '')
            tipo_evento = classificar_tipo_evento(fase_evento)
            
            if filtros.get('tipo') and tipo_evento != filtros['tipo']:
                continue
                
            if filtros.get('termo'):
                texto = discurso.get('transcricao', '') or discurso.get('sumario', '')
                if filtros['termo'].lower() not in texto.lower():
                    continue
            
            discursos_filtrados.append({
                **info_deputado,
                'data': discurso.get('dataHoraInicio', '').split('T')[0],
                'hora': discurso.get('dataHoraInicio', '').split('T')[1][:5] if 'T' in discurso.get('dataHoraInicio', '') else '',
                'sumario': discurso.get('transcricao', '')[:500] + '...' if len(discurso.get('transcricao', '')) > 500 else discurso.get('transcricao', ''),
                'transcricao_completa': discurso.get('transcricao', ''),
                'evento': tipo_evento,
                'id_discurso': discurso.get('id', '')
            })
            
        return discursos_filtrados
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
        termo = request.args.get('termo', '')
        partido = request.args.get('partido', '')
        estado = request.args.get('estado', '')
        periodo = int(request.args.get('periodo', '30'))
        tipo = request.args.get('tipo', '')
        deputado_id = request.args.get('deputado_id', '')
        pagina = int(request.args.get('pagina', '1'))
        itens_por_pagina = 10
        
        data_fim = datetime.now()
        data_inicio = data_fim - timedelta(days=periodo)
        
        filtros = {
            'termo': termo,
            'partido': partido,
            'estado': estado,
            'tipo': tipo,
            'data_inicio': data_inicio.strftime('%Y-%m-%d'),
            'data_fim': data_fim.strftime('%Y-%m-%d')
        }
        
        todos_discursos = []
        
        if deputado_id:
            # Se tiver ID do deputado, busca apenas os discursos dele
            todos_discursos = buscar_discursos_deputado(deputado_id, filtros)
        else:
            # Reduce the scope - only search if partido or estado is specified
            if not (partido or estado):
                return jsonify({
                    'total': 0,
                    'discursos': [],
                    'message': 'Por favor, selecione um partido ou estado para refinar sua busca'
                })
            
            try:
                deputados = get_deputados({'partido': partido, 'estado': estado})
                
                # Further reduce the number of deputies
                with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    futures = []
                    for deputado in deputados[:5]:  # Reduce to only 5 deputies
                        future = executor.submit(
                            buscar_discursos_deputado, 
                            deputado['id'],
                            filtros
                        )
                        futures.append(future)
                    
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            discursos = future.result()
                            todos_discursos.extend(discursos)
                        except Exception as e:
                            print(f"Erro ao processar discursos de deputado: {e}")
                            continue
                            
            except Exception as e:
                print(f"Erro ao buscar deputados: {e}")
                return jsonify({
                    'total': 0,
                    'discursos': [],
                    'message': 'Por favor, tente uma busca mais específica'
                }), 200  # Return 200 instead of 500
        
        # Filtra por termo se especificado
        if termo:
            todos_discursos = [
                discurso for discurso in todos_discursos
                if termo.lower() in discurso.get('sumario', '').lower() or 
                   termo.lower() in discurso.get('transcricao_completa', '').lower()
            ]
        
        # Ordena por data/hora
        todos_discursos.sort(key=lambda x: x['data'] + x['hora'], reverse=True)
        
        # Aplica paginação
        inicio = (pagina - 1) * itens_por_pagina
        fim = inicio + itens_por_pagina
        
        return jsonify({
            'total': len(todos_discursos),
            'discursos': todos_discursos[inicio:fim]
        })
        
    except Exception as e:
        print(f"Erro na busca: {e}")
        return jsonify({'error': 'Erro ao realizar busca'}), 500

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
