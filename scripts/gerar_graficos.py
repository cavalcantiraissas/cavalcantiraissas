"""
Gera os gráficos do README do perfil a partir da API do GitHub.

Saída (em assets/), cada uma nas versões clara e escura:
    numeros-{tema}.svg          repositórios, contribuições, commits e estrelas
    linguagens-{tema}.svg       participação de cada linguagem nos repositórios públicos
    repo-{nome}-{tema}.svg      cartão de cada repositório em destaque

Só usa a biblioteca padrão. Roda no GitHub Actions (variável GH_TOKEN) e
localmente (GH_TOKEN ou GITHUB_TOKEN). Considera apenas repositórios públicos.

Uso:
    GH_TOKEN=... python3 scripts/gerar_graficos.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from html import escape
from pathlib import Path

USUARIO = "cavalcantiraissas"
SAIDA = Path(__file__).resolve().parent.parent / "assets"

# Repositórios com cartão no README, na ordem em que aparecem.
DESTAQUES = [
    "rag-gemini-minimalista",
    "wbs-generator-gemini",
    "Ciencia-da-Computacao_UFMT",
    "novashop_case",
    "Dados_Ambientais_INPP",
    "Automatizando_com_Python",
]
# O próprio repositório do perfil não entra nas estatísticas de linguagens.
IGNORAR = {USUARIO}
MAX_LINGUAGENS = 8  # o resto vira "Outras"

# Cores dos dois temas do GitHub; a barra é o azul do slot 1 da paleta validada.
TEMAS = {
    "claro": {"fundo": "#ffffff", "borda": "#d0d7de", "texto": "#1f2328",
              "texto2": "#59636e", "trilho": "#eff2f5", "barra": "#2a78d6"},
    "escuro": {"fundo": "#0d1117", "borda": "#30363d", "texto": "#e6edf3",
               "texto2": "#9198a1", "trilho": "#161b22", "barra": "#3987e5"},
}
# Cor de identidade de cada linguagem (a mesma do GitHub), só no ponto ao lado do nome.
COR_LINGUAGEM = {
    "Python": "#3572A5", "C": "#555555", "C++": "#f34b7d", "Java": "#b07219",
    "HTML": "#e34c26", "Assembly": "#6E4C13", "PLpgSQL": "#336790",
    "JavaScript": "#f1e05a", "CSS": "#663399", "Shell": "#89e051",
    "Makefile": "#427819", "TypeScript": "#3178c6", "Jupyter Notebook": "#DA5B0B",
}
FONTE = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"


# ---------------------------------------------------------------------------
# API do GitHub
# ---------------------------------------------------------------------------

def _token() -> str:
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        sys.exit("Defina GH_TOKEN (ou GITHUB_TOKEN) para consultar a API do GitHub.")
    return token


def _requisicao(url: str, corpo: dict | None = None) -> dict | list:
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dados, headers={
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USUARIO}-readme",
    })
    with urllib.request.urlopen(req, timeout=30) as resposta:
        return json.load(resposta)


def repositorios_publicos() -> list[dict]:
    repos, pagina = [], 1
    while True:
        lote = _requisicao(f"https://api.github.com/users/{USUARIO}/repos?type=owner&per_page=100&page={pagina}")
        repos += [r for r in lote if not r["private"] and not r["fork"]]
        if len(lote) < 100:
            return repos
        pagina += 1


def contribuicoes() -> tuple[int, int]:
    """Contribuições e commits públicos dos últimos 12 meses.

    As contas privadas são descontadas para o resultado ser o mesmo com qualquer
    token (o pessoal, localmente, ou o GITHUB_TOKEN do Actions).
    """
    consulta = """query($login: String!) { user(login: $login) { contributionsCollection {
        contributionCalendar { totalContributions }
        restrictedContributionsCount
        commitContributionsByRepository(maxRepositories: 100) {
            repository { isPrivate } contributions { totalCount } } } } }"""
    resposta = _requisicao("https://api.github.com/graphql",
                           {"query": consulta, "variables": {"login": USUARIO}})
    coll = resposta["data"]["user"]["contributionsCollection"]
    publicas = coll["contributionCalendar"]["totalContributions"] - coll["restrictedContributionsCount"]
    commits = sum(item["contributions"]["totalCount"] for item in coll["commitContributionsByRepository"]
                  if not item["repository"]["isPrivate"])
    return publicas, commits


# ---------------------------------------------------------------------------
# Desenho
# ---------------------------------------------------------------------------

def _svg(largura: int, altura: int, tema: dict, titulo: str, corpo: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{largura}" height="{altura}" '
            f'viewBox="0 0 {largura} {altura}" role="img" aria-label="{escape(titulo)}">'
            f'<title>{escape(titulo)}</title>'
            f'<rect x="0.5" y="0.5" width="{largura - 1}" height="{altura - 1}" rx="8" '
            f'fill="{tema["fundo"]}" stroke="{tema["borda"]}"/>'
            f'<g font-family="{FONTE}">{corpo}</g></svg>')


def _numero(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def svg_numeros(tema: dict, valores: list[tuple[str, int]]) -> str:
    """Linha de números em destaque: valor grande, rótulo pequeno embaixo."""
    largura, altura = 840, 120
    coluna = largura / len(valores)
    corpo = ""
    for i, (rotulo, valor) in enumerate(valores):
        x = coluna * i + coluna / 2
        corpo += (f'<text x="{x:.0f}" y="62" text-anchor="middle" font-size="36" font-weight="600" '
                  f'fill="{tema["texto"]}">{_numero(valor)}</text>'
                  f'<text x="{x:.0f}" y="90" text-anchor="middle" font-size="14" '
                  f'fill="{tema["texto2"]}">{escape(rotulo)}</text>')
        if i:
            corpo += (f'<line x1="{coluna * i:.0f}" y1="30" x2="{coluna * i:.0f}" y2="94" '
                      f'stroke="{tema["borda"]}"/>')
    return _svg(largura, altura, tema, "Números do perfil no GitHub", corpo)


def svg_linguagens(tema: dict, linguagens: list[tuple[str, float]]) -> str:
    """Barras horizontais, uma série, ordenadas; o percentual fica na ponta de cada barra."""
    largura, topo, passo, espessura = 840, 64, 30, 14
    rotulo_x, barra_x = 24, 170
    barra_max = largura - barra_x - 90
    altura = topo + passo * len(linguagens) + 34
    maior = linguagens[0][1]
    corpo = (f'<text x="24" y="36" font-size="18" font-weight="600" fill="{tema["texto"]}">'
             f'Linguagens nos repositórios públicos</text>')
    for i, (nome, pct) in enumerate(linguagens):
        y = topo + passo * i
        cor = COR_LINGUAGEM.get(nome, tema["texto2"])
        comprimento = max(barra_max * pct / maior, 4)
        meio = y + espessura / 2
        corpo += (
            f'<circle cx="{rotulo_x + 5}" cy="{meio}" r="5" fill="{cor}"/>'
            f'<text x="{rotulo_x + 18}" y="{meio + 5}" font-size="14" fill="{tema["texto"]}">{escape(nome)}</text>'
            f'<rect x="{barra_x}" y="{y}" width="{barra_max}" height="{espessura}" rx="4" fill="{tema["trilho"]}"/>'
            # ponta arredondada e base reta: retângulo arredondado + quadrado cobrindo o início
            f'<rect x="{barra_x}" y="{y}" width="{comprimento:.1f}" height="{espessura}" rx="4" fill="{tema["barra"]}"/>'
            f'<rect x="{barra_x}" y="{y}" width="{min(comprimento, 4):.1f}" height="{espessura}" fill="{tema["barra"]}"/>'
            f'<text x="{barra_x + comprimento + 8:.1f}" y="{meio + 5}" font-size="13" '
            f'fill="{tema["texto2"]}">{f"{pct:.1f}".replace(".", ",")}%</text>'
        )
    corpo += (f'<text x="24" y="{altura - 14}" font-size="11" fill="{tema["texto2"]}">'
              f'Participação em bytes de código, por linguagem (atualizado diariamente)</text>')
    return _svg(largura, altura, tema, "Linguagens mais usadas nos repositórios públicos", corpo)


def _quebra(texto: str, limite: int, linhas: int) -> list[str]:
    palavras, saida, atual = texto.split(), [], ""
    for p in palavras:
        if len(atual) + len(p) + 1 > limite:
            saida.append(atual)
            atual = p
            if len(saida) == linhas:
                break
        else:
            atual = f"{atual} {p}".strip()
    else:
        saida.append(atual)
    if len(saida) > linhas or (len(saida) == linhas and atual and atual not in saida):
        saida = saida[:linhas]
        saida[-1] = saida[-1].rstrip(".,;:") + "…"
    return saida


def svg_repositorio(tema: dict, repo: dict) -> str:
    """Cartão de atalho: nome, descrição, linguagem principal e estrelas."""
    largura, altura = 410, 150
    linguagem = repo.get("language") or "—"
    cor = COR_LINGUAGEM.get(linguagem, tema["texto2"])
    descricao = _quebra(repo.get("description") or "", 56, 3)
    corpo = (f'<text x="20" y="34" font-size="16" font-weight="600" fill="{tema["barra"]}">'
             f'{escape(repo["name"])}</text>')
    for i, linha in enumerate(descricao):
        corpo += (f'<text x="20" y="{60 + 19 * i}" font-size="13" fill="{tema["texto2"]}">'
                  f'{escape(linha)}</text>')
    corpo += (f'<circle cx="26" cy="{altura - 22}" r="6" fill="{cor}"/>'
              f'<text x="38" y="{altura - 17}" font-size="13" fill="{tema["texto"]}">{escape(linguagem)}</text>'
              f'<text x="{largura - 20}" y="{altura - 17}" text-anchor="end" font-size="13" '
              f'fill="{tema["texto2"]}">★ {repo["stargazers_count"]}</text>')
    return _svg(largura, altura, tema, f'Repositório {repo["name"]}', corpo)


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

def main() -> None:
    SAIDA.mkdir(exist_ok=True)
    repos = repositorios_publicos()
    por_nome = {r["name"]: r for r in repos}

    total_linguagens: dict[str, int] = {}
    for r in repos:
        if r["name"] in IGNORAR:
            continue
        for nome, bytes_ in _requisicao(r["languages_url"]).items():
            total_linguagens[nome] = total_linguagens.get(nome, 0) + bytes_
    soma = sum(total_linguagens.values())
    ordenadas = sorted(total_linguagens.items(), key=lambda item: item[1], reverse=True)
    linguagens = [(n, 100 * b / soma) for n, b in ordenadas[:MAX_LINGUAGENS]]
    resto = sum(b for _, b in ordenadas[MAX_LINGUAGENS:])
    if resto:
        linguagens.append(("Outras", 100 * resto / soma))

    publicas, commits = contribuicoes()
    numeros = [
        ("repositórios públicos", len(repos)),
        ("contribuições em 12 meses", publicas),
        ("commits em 12 meses", commits),
        ("estrelas recebidas", sum(r["stargazers_count"] for r in repos)),
    ]

    for nome_tema, tema in TEMAS.items():
        (SAIDA / f"numeros-{nome_tema}.svg").write_text(svg_numeros(tema, numeros), encoding="utf-8")
        (SAIDA / f"linguagens-{nome_tema}.svg").write_text(svg_linguagens(tema, linguagens), encoding="utf-8")
        for nome in DESTAQUES:
            if nome in por_nome:
                (SAIDA / f"repo-{nome}-{nome_tema}.svg").write_text(
                    svg_repositorio(tema, por_nome[nome]), encoding="utf-8")
            else:
                print(f"[aviso] repositório em destaque não encontrado: {nome}")

    print("Números:", ", ".join(f"{r}={v}" for r, v in numeros))
    print("Linguagens:", ", ".join(f"{n} {p:.1f}%" for n, p in linguagens))


if __name__ == "__main__":
    main()
