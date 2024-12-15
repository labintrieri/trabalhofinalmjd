from flask import Flask, render_template, request, jsonify
import requests
from datetime import datetime, timedelta
import concurrent.futures
from urllib.parse import quote
import json

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

def atualizar_cache():
    """Atualiza o cache de dados básicos se necessário"""
    agora = datetime.now()
    
    if not CACHE['cache_time'] or (agora - CACHE['cache_time']).total_seconds() > 86400:  # 24 horas
        try:
            # Busca lista de partidos
            response = requests.get('https://dadosabertos.camara.leg.br/api/v2/partidos?ordem=ASC&ordenarPor=sigla', timeout=10)  # Increased timeout
            response.raise_for_status()
            dados = response.json()
            if 'dados' in dados:
                CACHE['partidos'] = [
                    {'sigla': partido['sigla']} 
                    for partido in dados['dados'] 
                    if partido.get('sigla') and partido.get('status', {}).get('situacao') == 'Ativo'
                ]
            else:
                CACHE['partidos'] = PARTIDOS_ATIVOS
            
            CACHE['cache_time'] = agora
            
        except Exception as e:
            print(f"Erro ao atualizar cache: {e}")
            CACHE['partidos'] = PARTIDOS_ATIVOS  # Fallback to predefined list
            CACHE['cache_time'] = agora

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
        response = requests.get(url, params=params, timeout=10)  # Increased timeout
        response.raise_for_status()
        return response.json()['dados']
    except Exception as e:
        print(f"Erro ao buscar deputados: {e}")
        return []  # Return empty list on error

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
        # Busca informações do deputado
        url_deputado = f"https://dadosabertos.camara.leg.br/api/v2/deputados/{id_deputado}"
        dep_response = requests.get(url_deputado)
        dep_data = dep_response.json()['dados']
        
        info_deputado = {
            'nome': dep_data['ultimoStatus']['nomeEleitoral'],
            'partido': dep_data['ultimoStatus']['siglaPartido'],
            'estado': dep_data['ultimoStatus']['siglaUf'],
            'foto': dep_data['ultimoStatus']['urlFoto'],
            'id': id_deputado
        }
        
        # Busca discursos
        response = requests.get(url, params=params)
        response.raise_for_status()
        discursos = response.json()['dados']
        
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
            # Caso contrário, busca por todos os deputados que correspondam aos filtros
            try:
                deputados = get_deputados({'partido': partido, 'estado': estado})
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    futures = []
                    for deputado in deputados[:20]:  # Limita a 20 deputados por vez
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
                return jsonify({'error': 'Erro ao buscar deputados'}), 500
        
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
