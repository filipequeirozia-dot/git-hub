# Dashboard Financeiro Matinal — Documentação Completa

> Guia de referência para modificar dados, fontes, visual e análise IA do dashboard.
> Atualizado em: 2026-05-09

---

## Sumário

1. [Visão geral](#visão-geral)
2. [Estrutura de arquivos](#estrutura-de-arquivos)
3. [Como rodar](#como-rodar)
4. [Configuração de API Keys](#configuração-de-api-keys)
5. [Fontes de dados](#fontes-de-dados)
6. [Como modificar cada seção do dashboard](#como-modificar-cada-seção-do-dashboard)
7. [Como modificar o visual (cores, layout, fontes)](#como-modificar-o-visual)
8. [Como modificar a análise por IA](#como-modificar-a-análise-por-ia)
9. [Troubleshooting](#troubleshooting)
10. [Histórico de decisões técnicas](#histórico-de-decisões-técnicas)

---

## Visão geral

Script Python que:
1. Coleta dados de mercado em tempo real (Yahoo Finance + brapi.dev)
2. Faz scraping de notícias financeiras brasileiras (5 fontes diretas + Apify)
3. Chama Claude AI para gerar análise executiva
4. Gera dashboard HTML dark mode premium e abre no navegador

**Arquivo principal:** `dashboard_mercado.py` (~1100 linhas, autocontido — todo HTML/CSS é gerado inline)

---

## Estrutura de arquivos

```
Dashboard mercado financeiro/
├── dashboard_mercado.py       Script principal — TUDO está aqui
├── requirements.txt           Dependências Python
├── .env                       Chaves API (NÃO COMMITAR)
├── .env.example               Template das chaves
├── .gitignore                 Protege .env
├── RODAR_DASHBOARD.bat        Atalho duplo-clique para rodar
├── instalar_dependencias.bat  Instala dependências Python
├── agendar_task_windows.bat   Agenda execução automática às 07:30
├── DOCUMENTACAO.md            Este arquivo
└── output/
    ├── dashboard_latest.html         Sempre o mais recente
    └── dashboard_YYYYMMDD_HHMM.html  Histórico
```

---

## Como rodar

### Opção 1 — Duplo-clique
Duplo-clique em `RODAR_DASHBOARD.bat`

### Opção 2 — Terminal
```bash
cd "C:\Users\Windows\Desktop\W1-CAPITAL\Pasta Claud\Dashboard\Dashboard mercado financeiro"
python dashboard_mercado.py
```

### Opção 3 — Agendar execução automática
Execute como administrador: `agendar_task_windows.bat`
Roda todo dia útil às 07:30

---

## Configuração de API Keys

Arquivo: `.env` na raiz do projeto.

```bash
# Obrigatória para análise IA — https://console.anthropic.com/settings/keys
ANTHROPIC_API_KEY=sk-ant-api03-...

# Opcional mas recomendada — premium news via Google Search
# https://console.apify.com/account/integrations
APIFY_TOKEN=apify_api_...

# Opcional — só se passar dos limites grátis do brapi
BRAPI_TOKEN=
```

### Custos estimados (rodando 1×/dia)
- **Anthropic Claude Sonnet 4.5:** ~US$ 0,01 por execução = ~US$ 0,30/mês
- **Apify rag-web-browser:** consome créditos free tier (US$ 5 grátis/mês geralmente cobre)

### Comportamento por configuração

| ANTHROPIC | APIFY | "O que o investidor precisa saber" |
|-----------|-------|------------------------------------|
| ❌        | ❌    | Apenas snapshot do dia (Ibovespa, Dólar, S&P) |
| ❌        | ✅    | Manchetes reais da semana com fonte |
| ✅        | ✅    | Análise IA com bullets analíticos profissionais |

---

## Fontes de dados

### Dados de mercado (cotações em tempo real)

| Símbolo     | O que é          | Fonte         | Função no código          |
|-------------|------------------|---------------|---------------------------|
| `^BVSP`     | Ibovespa         | Yahoo Finance | `yf_quote()` linha ~155   |
| `USDBRL=X`  | Dólar/Real       | Yahoo Finance | `yf_quote()`              |
| `^GSPC`     | S&P 500          | Yahoo Finance | `yf_quote()`              |
| `^IXIC`     | Nasdaq           | Yahoo Finance | `yf_quote()`              |
| `BTC-USD`   | Bitcoin          | Yahoo Finance | `yf_quote()`              |
| `BZ=F`      | Petróleo Brent   | Yahoo Finance | `yf_quote()`              |
| `GC=F`      | Ouro             | Yahoo Finance | `yf_quote()`              |
| Top altas/baixas Ibovespa | brapi.dev | `fetch_top_movers()` linha ~190 |

### Fontes de notícias

| Fonte             | Tipo            | Função             | Status   |
|-------------------|-----------------|--------------------|----------|
| Money Times       | Scraper direto  | `scrape_money_times()`     | ✅ ativo |
| Seu Dinheiro      | Scraper direto  | `scrape_seu_dinheiro()`    | ✅ ativo |
| Bom Dia Mercado   | Scraper direto  | `scrape_bom_dia_mercado()` | ✅ ativo |
| E-Investidor      | Scraper direto  | `scrape_einvestidor()`     | ✅ ativo |
| Valor Investe     | Scraper direto  | `scrape_valor_investe()`   | ⚠️ instável |
| **Apify (Google News)** | API premium | `fetch_apify_news()`      | ✅ via APIFY_TOKEN |
| **Apify (Eventos da semana)** | API premium | `fetch_weekly_market_events()` | ✅ via APIFY_TOKEN |

> Removidos: XP Morning Call e Investing.com BR (ambos retornam 403 anti-bot)

---

## Como modificar cada seção do dashboard

### Seção 1 — KPIs em tempo real (Ibovespa, Dólar, S&P, etc.)

**Onde modificar:** função `fetch_market_data()` em `dashboard_mercado.py`

**Adicionar novo índice/cotação:**
1. Encontre a linha:
   ```python
   symbols = ["^BVSP", "USDBRL=X", "^GSPC", "^IXIC", "BTC-USD", "BZ=F", "GC=F"]
   ```
2. Adicione o símbolo do Yahoo Finance (ex: `EURBRL=X` para Euro/Real)
3. Adicione um `_extract()` no return:
   ```python
   euro = _extract("EURBRL=X", is_brl=True)
   return {
       ...,
       "euro": euro,
   }
   ```
4. Adicione o card no HTML — função `generate_html()`:
   ```python
   kpi_euro = _kpi_card("Euro / Real", f"{euro['price']:.4f}", euro["change"], "💶", "R$ ")
   ```
5. Inclua `{kpi_euro}` no HTML do `kpi-grid`

### Seção 2 — "O que o investidor precisa saber" (Análise IA)

**Onde modificar:** função `generate_ai_analysis()` em `dashboard_mercado.py`

- **Prompt da IA:** procure pela string que começa com `"Você é um analista de mercado financeiro sênior brasileiro com 20 anos de experiência."`
- **Fallback (sem IA):** função `_build_fallback_analysis()` — usa headlines do Apify diretamente
- **Quantidade de bullets:** ajuste no prompt no JSON template (`executive_summary`)

### Seção 3 — Morning Call

**Onde modificar:** parâmetros da query Apify em `collect_all_news()`

```python
apify_morning = fetch_apify_news("morning call mercado abertura bolsa hoje", take=5)
```

Mude o termo de busca ou número de resultados.

### Seção 4 — Top Altas e Baixas Ibovespa

**Onde modificar:** função `fetch_top_movers()` em `dashboard_mercado.py`

- Lista de blue chips no fallback: tickers como `PETR4`, `VALE3`, `ITUB4`, etc.
- Para mostrar mais que 5 ações: ajuste o slice `[:5]` na função

### Seção 5 — Notícias em destaque (cards)

**Onde modificar:** função `collect_all_news()`

Para limitar quantos cards aparecem:
```python
return morning_call_news, all_news[:15], weekly_events  # mude :15 para :20, :30, etc.
```

Para reordenar prioridade das fontes (qual aparece primeiro):
```python
for item in (apify_market + bdm_news + mt_news + sd_news + ei_news + vi_news):
```
Reordene esta concatenação.

### Seção 6 — Resumo Semanal (colapsável)

**Onde modificar:** função `fetch_weekly_market_events()` em `dashboard_mercado.py`

Queries usadas (linha ~430):
```python
queries = [
    "Ibovespa fechou semana balanço alta queda esta semana",
    "Copom Selic Banco Central decisão impacto mercado esta semana",
    "ações destaques semana resultados balanço empresas Brasil",
    "fundos imobiliários FIIs semana destaque rendimento",
]
```

Para adicionar tópico (ex: criptomoedas):
```python
queries.append("Bitcoin criptomoedas semana destaque alta queda Brasil")
```

---

## Como modificar o visual

Todo CSS está dentro da função `generate_html()` em uma string `<style>...</style>`.

### Cores do tema

Procure por `:root {` na função. Edite as variáveis CSS:

```css
:root {
  --bg: #0a0a0f;        /* fundo geral */
  --card: #12121a;      /* cards */
  --card2: #1a1a26;     /* cards secundários */
  --border: #1e1e2e;    /* bordas */
  --text: #e2e8f0;      /* texto */
  --muted: #64748b;     /* texto secundário */
  --green: #22c55e;     /* alta / positivo */
  --red: #ef4444;       /* baixa / negativo */
  --blue: #3b82f6;
  --purple: #8b5cf6;
  --orange: #f97316;
}
```

### Cores das fontes de notícias (badges)

Procure por `SOURCE_COLORS = {` em `dashboard_mercado.py`:

```python
SOURCE_COLORS = {
    "Money Times": "#f59e0b",       # laranja
    "Bom Dia Mercado": "#00b4d8",   # azul ciano
    "Seu Dinheiro": "#10b981",      # verde
    "E-Investidor": "#2d6a4f",      # verde escuro
    "Valor Investe": "#7209b7",     # roxo
}
```

Para adicionar nova fonte: adicione em `SOURCE_COLORS` e `SOURCE_BG` (com mesma cor mas com `rgba(...,0.15)` para o fundo).

### Logos / ícones (emojis)

No código os ícones são emojis Unicode. Para trocar:
- KPIs (Ibovespa, Dólar, etc.) — busque por `_kpi_card("Ibovespa"` e ajuste o ícone
- Headers de seção — busque por `section-title` no HTML

### Tamanho da fonte / layout

CSS dentro de `generate_html()`:
- `.container { max-width: 1400px }` — largura máxima
- `.kpi-grid { grid-template-columns: repeat(auto-fit, minmax(180px,1fr)) }` — tamanho mínimo dos cards de KPI
- `.news-grid { grid-template-columns: repeat(auto-fill, minmax(300px,1fr)) }` — cards de notícias

### Header (título + data)

Procure por `<!-- HEADER -->` na função `generate_html()`.

```html
<h1>📊 Briefing Matinal — Mercado Financeiro</h1>
```

### Footer (fontes + disclaimer)

Procure por `<!-- FOOTER -->` na função `generate_html()`.

Para adicionar nova fonte no footer:
```html
<a href="https://novasite.com" target="_blank">Nova Fonte</a>
```

---

## Como modificar a análise por IA

### Mudar o tom / personalidade do analista

Em `generate_ai_analysis()`, edite a primeira frase do prompt:

```python
prompt = f"""Você é um analista de mercado financeiro sênior brasileiro com 20 anos de experiência.
```

Exemplos:
- Mais técnico: `"Você é um analista quantitativo com PhD em Finanças..."`
- Mais didático: `"Você é um educador financeiro que explica conceitos de mercado para pessoas físicas..."`
- Mais agressivo/direto: `"Você é um trader experiente que vai direto ao ponto..."`

### Mudar quantidade ou tipo de bullets

No template JSON dentro do prompt:

```python
"executive_summary": [
    "bullet 1 — PRINCIPAIS ACONTECIMENTOS DA SEMANA...",
    ...5 bullets
],
```

Para 7 bullets: adicione mais entradas na lista.

### Mudar o modelo Claude

Linha ~712 em `dashboard_mercado.py`:

```python
model="claude-sonnet-4-5",
```

Modelos disponíveis (mais recentes em 2026):
- `claude-opus-4-7` — mais inteligente, mais caro (~10× preço)
- `claude-sonnet-4-6` — equilibrio
- `claude-sonnet-4-5` — atual (recomendado)
- `claude-haiku-4-5` — mais rápido e barato (~3× mais barato)

### Custo estimado por modelo (por execução)

- Opus: ~US$ 0,10
- Sonnet: ~US$ 0,01
- Haiku: ~US$ 0,003

---

## Troubleshooting

### Erro: "ANTHROPIC_API_KEY não configurado"
Causa: variável de ambiente do sistema sobrescrevendo `.env`.
**Já corrigido** com `load_dotenv(override=True)`. Se voltar a acontecer, verifique se a key no `.env` está sem espaços/aspas.

### Erro: "401 Invalid authentication credentials"
A key está errada ou foi revogada. Gere nova em https://console.anthropic.com/settings/keys e cole no `.env`.

### Erro: Dashboard mostra "configure ANTHROPIC_API_KEY"
A IA falhou. Possíveis causas:
- Sem créditos na conta Anthropic
- Key inválida
- Rate limit atingido (raro)

Solução: verificar console.anthropic.com → Plans & Billing.

### Apify retorna 0 notícias
Causas possíveis:
- Sem créditos no Apify (free tier US$ 5/mês)
- Token errado
- Actor temporariamente indisponível

Solução: testar em https://console.apify.com → veja runs recentes.

### brapi.dev retorna 401
Causa: brapi começou a exigir token para alguns endpoints.
**Já mitigado** usando Yahoo Finance para índices globais.
Se top movers parar de funcionar, gere token grátis em https://brapi.dev e adicione `BRAPI_TOKEN` no `.env`.

### Scraper de notícia retorna 403
Site começou a bloquear bots (aconteceu com XP e Investing).
Solução: o Apify (rag-web-browser) consegue acessar via Google Search.

### Dashboard não abre no navegador
- Verifique se o arquivo `output/dashboard_latest.html` foi gerado
- Abra manualmente: duplo-clique no `.html`
- Windows pode estar bloqueando `webbrowser.open()` — abra manualmente

### Caracteres com encoding errado no terminal
**Já corrigido** com `sys.stdout = io.TextIOWrapper(...)` no início do script.

---

## Histórico de decisões técnicas

### Por que Yahoo Finance + brapi.dev em vez de só uma API?

- **Yahoo Finance v8** (`query1.finance.yahoo.com/v8/finance/chart/`): endpoint público sem auth para cotações de índices globais (`^BVSP`, `^GSPC`, etc.)
- **brapi.dev**: única API gratuita BR-friendly para Top Altas/Baixas do Ibovespa em tempo real
- brapi começou a bloquear endpoints de índice — solução foi usar Yahoo Finance para índices e brapi só para top movers

### Por que removi XP Morning Call e Investing.com?

Ambos retornam **403 Forbidden** desde meados de 2025 — Cloudflare anti-bot detecta scrapers Python.
Substituí por:
- **Money Times** + **Seu Dinheiro** (scrapers diretos que ainda funcionam)
- **Apify rag-web-browser** que faz busca via Google e contorna bloqueios

### Por que Apify rag-web-browser e não easyapi/google-news-scraper?

Testei `easyapi/google-news-scraper`: requer `maxItems >= 100`, mas com filtros pt-BR retornava 0 resultados consistentemente.
`apify/rag-web-browser` é o actor oficial da Apify, retorna top N resultados orgânicos do Google em formato markdown — funciona melhor.

### Por que carrego `.env` com `override=True`?

Algumas máquinas Windows têm `ANTHROPIC_API_KEY=""` no env do sistema (variável vazia mas existente). Sem `override=True`, o `os.getenv()` retorna a string vazia do sistema em vez do valor do `.env`.

### Por que o script é um arquivo único de ~1100 linhas?

Decisão deliberada para manter o projeto **autocontido e fácil de modificar**:
- Sem necessidade de imports relativos
- HTML/CSS inline = fácil ver onde mudar
- Para um script utilitário, modularizar adiciona complexidade sem ganho

---

## Comandos úteis

### Ver as últimas 10 execuções
```bash
ls -lt "output/dashboard_*.html" | head -10
```

### Limpar histórico (manter só `dashboard_latest.html`)
```bash
find output/ -name "dashboard_2*.html" -delete
```

### Testar uma fonte específica isoladamente
```bash
python -c "import dashboard_mercado as d; print(d.scrape_money_times())"
```

### Verificar se as keys estão funcionando
```bash
python -c "
from dotenv import load_dotenv
import os
load_dotenv(override=True)
print('Anthropic:', 'OK' if os.getenv('ANTHROPIC_API_KEY','').startswith('sk-ant') else 'FALHA')
print('Apify:', 'OK' if os.getenv('APIFY_TOKEN','').startswith('apify_api_') else 'FALHA')
"
```

---

## Contato e referências

- **Anthropic API:** https://docs.anthropic.com/en/api/getting-started
- **Apify Console:** https://console.apify.com
- **brapi.dev docs:** https://brapi.dev/docs
- **Yahoo Finance API (não oficial):** `https://query1.finance.yahoo.com/v8/finance/chart/{symbol}`
