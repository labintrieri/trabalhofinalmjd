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

def atualizar_cache():
    """Atualiza o cache de dados básicos se necessário"""
    agora = datetime.now()
    
    if not CACHE['cache_time'] or (agora - CACHE['cache_time']).total_seconds() > 86400:  # 24 horas
        try:
            # Busca lista de partidos
            response = requests.get('https://dadosabertos.camara.leg.br/api/v2/partidos')
            response.raise_for_status()  # Levanta exceção em caso de erro HTTP
            CACHE['partidos'] = response.json()['dados']
            
            # Lista de estados brasileiros
            CACHE['estados'] = [
                {"sigla": "AC"}, {"sigla": "AL"}, {"sigla": "AP"}, {"sigla": "AM"},
                {"sigla": "BA"}, {"sigla": "CE"}, {"sigla": "DF"}, {"sigla": "ES"},
                {"sigla": "GO"}, {"sigla": "MA"}, {"sigla": "MT"}, {"sigla": "MS"},
                {"sigla": "MG"}, {"sigla": "PA"}, {"sigla": "PB"}, {"sigla": "PR"},
                {"sigla": "PE"}, {"sigla": "PI"}, {"sigla": "RJ"}, {"sigla": "RN"},
                {"sigla": "RS"}, {"sigla": "RO"}, {"sigla": "RR"}, {"sigla": "SC"},
                {"sigla": "SP"}, {"sigla": "SE"}, {"sigla": "TO"}
            ]
            
            CACHE['cache_time'] = agora
            
        except requests.exceptions.RequestException as e:
            print(f"Erro ao atualizar cache: {e}")
            if not CACHE['partidos']:
                CACHE['partidos'] = []
                CACHE['estados'] = []

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
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()['dados']
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
@app.route('/buscar')
def buscar():
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
    
    if deputado_id:
        # Se tiver ID do deputado, busca apenas os discursos dele
        todos_discursos = buscar_discursos_deputado(deputado_id, filtros)
    else:
        # Caso contrário, mantém a busca normal
        deputados = get_deputados({'partido': partido, 'estado': estado})
        todos_discursos = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(
                    buscar_discursos_deputado, 
                    deputado['id'],
                    filtros
                )
                for deputado in deputados[:20]  # Limita a 20 deputados por vez
            ]
            
            for future in concurrent.futures.as_completed(futures):
                discursos = future.result()
                todos_discursos.extend(discursos)
    
    todos_discursos.sort(key=lambda x: x['data'] + x['hora'], reverse=True)
    resultado_paginado = aplicar_paginacao(todos_discursos, pagina, itens_por_pagina)
    
    return jsonify(resultado_paginado)

@app.route('/partidos')
def listar_partidos():
    atualizar_cache()
    return jsonify(CACHE['partidos'])

@app.route('/estados')
def listar_estados():
    atualizar_cache()
    return jsonify(CACHE['estados'])

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