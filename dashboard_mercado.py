#!/usr/bin/env python3
"""
Dashboard Diário de Mercado Financeiro — Briefing Matinal
Gera um dashboard HTML dark mode premium com dados em tempo real e análise IA.
"""

import os
import sys
import io
import json
import re
import time
import webbrowser
import tempfile
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Força UTF-8 no stdout/stderr para suportar emojis no terminal Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import anthropic

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# override=True garante que o .env tenha prioridade sobre variáveis do sistema
# (algumas máquinas têm ANTHROPIC_API_KEY vazio no env do sistema)
load_dotenv(override=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
BRAPI_TOKEN = os.getenv("BRAPI_TOKEN", "").strip()
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "").strip()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Principais blue chips da B3 (ações de maior relevância)
BR_BLUE_CHIPS = [
    "PETR3","PETR4","VALE3","ITUB4","BBDC4","ABEV3","WEGE3","RENT3",
    "BBAS3","SUZB3","ELET3","B3SA3","PRIO3","JBSS3","EMBR3","BPAC11",
    "RDOR3","EQTL3","CSAN3","RADL3","HAPV3","CPLE6","SBSP3","VIVT3",
    "CMIG4","GGBR4","ITSA4","BRFS3","ENEV3","AZUL4",
]

# Principais ações globais (NYSE/NASDAQ) — ticker: nome amigável
GLOBAL_STOCKS_MAP = {
    "AAPL":  "Apple",
    "MSFT":  "Microsoft",
    "GOOGL": "Alphabet",
    "AMZN":  "Amazon",
    "META":  "Meta",
    "TSLA":  "Tesla",
    "NVDA":  "NVIDIA",
    "JPM":   "JPMorgan",
    "V":     "Visa",
    "WMT":   "Walmart",
    "JNJ":   "Johnson & Johnson",
    "XOM":   "Exxon Mobil",
    "UNH":   "UnitedHealth",
    "BRK-B": "Berkshire Hath.",
    "BABA":  "Alibaba",
    "TSM":   "TSMC",
    "ASML":  "ASML",
    "NVO":   "Novo Nordisk",
    "SAP":   "SAP SE",
    "TM":    "Toyota",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(url: str, timeout: int = 12) -> Optional[requests.Response]:
    try:
        r = SESSION.get(url, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"  [WARN] GET {url[:60]}... → {e}")
        return None


def _soup(url: str) -> Optional[BeautifulSoup]:
    r = _get(url)
    if r:
        return BeautifulSoup(r.text, "lxml")
    return None


def _fmt_brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_usd(v: float) -> str:
    return f"$ {v:,.2f}"


def _sign(v: float) -> str:
    return "+" if v >= 0 else ""


# ---------------------------------------------------------------------------
# 1. Dados de mercado
# ---------------------------------------------------------------------------

YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def yf_quote(symbol: str) -> dict:
    """Busca cotação via Yahoo Finance v8 (sem autenticação)."""
    enc = requests.utils.quote(symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{enc}?interval=1d&range=2d"
    try:
        r = requests.get(url, headers=YF_HEADERS, timeout=12)
        r.raise_for_status()
        meta = r.json()["chart"]["result"][0]["meta"]
        prev = meta.get("chartPreviousClose") or meta.get("previousClose") or 0
        curr = meta.get("regularMarketPrice", 0)
        chg = ((curr - prev) / prev * 100) if prev else 0
        return {"price": curr, "change": chg, "prev_close": prev, "symbol": symbol}
    except Exception as e:
        print(f"  [WARN] yf_quote({symbol}): {e}")
        return {"price": 0, "change": 0, "prev_close": 0, "symbol": symbol}


def fetch_brapi(*symbols: str) -> dict:
    """Busca ações brasileiras via brapi.dev (funciona sem token para ações individuais)."""
    joined = ",".join(symbols)
    token_param = f"&token={BRAPI_TOKEN}" if BRAPI_TOKEN else ""
    url = f"https://brapi.dev/api/quote/{joined}?fundamental=false{token_param}"
    try:
        r = SESSION.get(url, timeout=12)
        r.raise_for_status()
        return {q["symbol"]: q for q in r.json().get("results", [])}
    except Exception as e:
        print(f"  [WARN] brapi {joined[:40]}: {e}")
        return {}


def fetch_top_movers() -> dict:
    """Busca top altas e baixas do Ibovespa via brapi /list (livre sem token)."""
    def _parse(order):
        url = f"https://brapi.dev/api/quote/list?sortBy=change&sortOrder={order}&limit=20&type=stock"
        r = _get(url)
        if not r:
            return []
        stocks = r.json().get("stocks", [])
        # Filtra penny stocks e sem volume para mostrar só ativos relevantes
        return [s for s in stocks if s.get("market_cap") and s.get("volume", 0) > 1000][:5]

    highs = _parse("desc")
    lows = _parse("asc")

    # Fallback com blue chips via brapi
    if not highs or not lows:
        tickers = [
            "PETR4","VALE3","ITUB4","BBDC4","ABEV3",
            "WEGE3","RENT3","BBAS3","SUZB3","ELET3",
            "MGLU3","BPAC11","RADL3","PRIO3","CPLE6",
        ]
        quotes = fetch_brapi(*tickers)
        items = [
            {
                "stock": sym,
                "name": q.get("shortName", sym),
                "change": q.get("regularMarketChangePercent", 0),
                "price": q.get("regularMarketPrice", 0),
            }
            for sym, q in quotes.items()
        ]
        items.sort(key=lambda x: x["change"], reverse=True)
        highs = items[:5]
        lows = list(reversed(items[-5:]))

    return {"highs": highs, "lows": lows}


def fetch_main_br_stocks() -> dict:
    """Busca altas e baixas entre as principais blue chips da B3."""
    print("  🇧🇷 Buscando principais blue chips da B3...")
    quotes = fetch_brapi(*BR_BLUE_CHIPS)
    items = []
    for sym, q in quotes.items():
        change = float(q.get("regularMarketChangePercent") or 0)
        price = float(q.get("regularMarketPrice") or 0)
        name = q.get("shortName") or q.get("longName") or sym
        if price > 0:
            items.append({"stock": sym, "name": name, "change": change, "price": price, "currency": "BRL"})
    items.sort(key=lambda x: x["change"], reverse=True)
    return {"highs": items[:5], "lows": items[-5:][::-1]}


def fetch_global_movers() -> dict:
    """Busca top altas e baixas globais via Yahoo Finance (batch)."""
    print("  🌍 Buscando principais ações globais...")
    symbols_str = ",".join(GLOBAL_STOCKS_MAP.keys())
    enc = requests.utils.quote(symbols_str)
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={enc}&lang=en-US&region=US"
    try:
        r = requests.get(url, headers=YF_HEADERS, timeout=15)
        r.raise_for_status()
        result = r.json().get("quoteResponse", {}).get("result", [])
        items = []
        for q in result:
            sym = q.get("symbol", "")
            price = float(q.get("regularMarketPrice") or 0)
            change = float(q.get("regularMarketChangePercent") or 0)
            name = GLOBAL_STOCKS_MAP.get(sym) or q.get("shortName") or sym
            if price > 0:
                items.append({"stock": sym, "name": name, "change": change, "price": price, "currency": "USD"})
        items.sort(key=lambda x: x["change"], reverse=True)
        return {"highs": items[:5], "lows": items[-5:][::-1]}
    except Exception as e:
        print(f"  [WARN] Global movers: {e}")
        return {"highs": [], "lows": []}


def fetch_market_data() -> dict:
    """Coleta todos os dados de mercado relevantes."""
    print("📊 Buscando dados de mercado...")
    # Índices e commodities via Yahoo Finance (sem auth)
    symbols = ["^BVSP", "USDBRL=X", "^GSPC", "^IXIC", "BTC-USD", "BZ=F", "GC=F"]
    quotes = {s: yf_quote(s) for s in symbols}

    def _extract(sym, is_brl=False):
        q = quotes.get(sym, {})
        return {
            "price": q.get("price", 0),
            "change": q.get("change", 0),
            "prev_close": q.get("prev_close", 0),
            "currency": "BRL" if is_brl else "USD",
        }

    bvsp = _extract("^BVSP")
    dolar = _extract("USDBRL=X", is_brl=True)
    sp500 = _extract("^GSPC")
    nasdaq = _extract("^IXIC")
    btc = _extract("BTC-USD")
    brent = _extract("BZ=F")
    gold = _extract("GC=F")

    br_main = fetch_main_br_stocks()
    global_mv = fetch_global_movers()

    return {
        "ibovespa": bvsp,
        "dolar": dolar,
        "sp500": sp500,
        "nasdaq": nasdaq,
        "bitcoin": btc,
        "brent": brent,
        "gold": gold,
        "br_main_highs": br_main.get("highs", []),
        "br_main_lows": br_main.get("lows", []),
        "global_highs": global_mv.get("highs", []),
        "global_lows": global_mv.get("lows", []),
        "timestamp": datetime.now().isoformat(),
    }


# ---------------------------------------------------------------------------
# 2. Scraping de notícias
# ---------------------------------------------------------------------------

def scrape_money_times() -> list[dict]:
    """Scrapa o Money Times — notícias de mercado financeiro brasileiro."""
    print("📰 Scraping Money Times...")
    soup = _soup("https://www.moneytimes.com.br/ultimas-noticias/")
    if not soup:
        return []
    news = []
    seen = set()
    for item in soup.select(".news-item")[:15]:
        link_el = item.select_one("a[href]")
        title_el = item.select_one("h2, h3, .title, .news-item-title")
        time_el = item.select_one("time, [class*='date']")
        if not link_el or not title_el:
            # Fallback: pega texto do próprio link
            if link_el and not title_el:
                title = link_el.get_text(strip=True)
            else:
                continue
        else:
            title = title_el.get_text(strip=True)
        href = link_el["href"] if link_el else ""
        if href.startswith("/"):
            href = "https://www.moneytimes.com.br" + href
        if not title or len(title) < 20 or title in seen:
            continue
        seen.add(title)
        pub_date = time_el.get_text(strip=True) if time_el else ""
        news.append({"title": title, "url": href, "source": "Money Times", "date": pub_date})
        if len(news) >= 5:
            break
    return news


def scrape_seu_dinheiro() -> list[dict]:
    """Scrapa o Seu Dinheiro — notícias de mercado e finanças."""
    print("📰 Scraping Seu Dinheiro...")
    soup = _soup("https://www.seudinheiro.com/mercado/")
    if not soup:
        return []
    news = []
    seen = set()
    for h in soup.select("article h2 a[href], article h3 a[href]")[:15]:
        title = h.get_text(strip=True)
        href = h.get("href", "")
        if href.startswith("/"):
            href = "https://www.seudinheiro.com" + href
        if not title or len(title) < 20 or title in seen:
            continue
        seen.add(title)
        news.append({"title": title, "url": href, "source": "Seu Dinheiro", "date": ""})
        if len(news) >= 5:
            break
    return news


def _domain_to_source(url: str) -> str:
    """Converte URL em nome de fonte legível (ex: 'infomoney.com.br' → 'InfoMoney')."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.replace("www.", "")
        # Mapeamento de domínios conhecidos
        known = {
            "infomoney.com.br": "InfoMoney",
            "valor.globo.com": "Valor Econômico",
            "valorinveste.globo.com": "Valor Investe",
            "moneytimes.com.br": "Money Times",
            "seudinheiro.com": "Seu Dinheiro",
            "exame.com": "Exame",
            "suno.com.br": "Suno",
            "einvestidor.estadao.com.br": "E-Investidor",
            "estadao.com.br": "Estadão",
            "g1.globo.com": "G1",
            "uol.com.br": "UOL",
            "folha.uol.com.br": "Folha de S.Paulo",
            "agora.folha.uol.com.br": "Folha · Agora",
            "cnnbrasil.com.br": "CNN Brasil",
            "reuters.com": "Reuters",
            "bloomberg.com": "Bloomberg",
            "investing.com": "Investing.com",
            "br.investing.com": "Investing.com BR",
            "neofeed.com.br": "NeoFeed",
            "brazilian.report": "Brazilian Report",
            "braziljournal.com": "Brazil Journal",
            "ecoinvestidor.com.br": "Eco Investidor",
            "b3.com.br": "B3",
        }
        if host in known:
            return known[host]
        # Pega só o dominio principal sem TLD
        parts = host.split(".")
        return parts[0].title() if parts else host
    except Exception:
        return "Web"


# Padrões de títulos genéricos (homepages, categorias) que NÃO são manchetes
GENERIC_TITLE_PATTERNS = [
    r"^(notícias|notícia|últimas|principais)\b",
    r"\b(home|homepage|página inicial|category|categoria)\b",
    r"^(mercados?|mercado financeiro|bolsa|economia)\s*[-–|]",
    r"^(b3|infomoney|investing|valor|exame|moneytimes|seu dinheiro|expert xp)",
    r"calendário\s+econômico",
    r"^(sobre|contato|política)",
]


def _is_generic_title(title: str) -> bool:
    """Detecta títulos genéricos (homepages/categorias) vs manchetes reais."""
    t = title.lower().strip()
    if len(t) < 25:
        return True
    for pat in GENERIC_TITLE_PATTERNS:
        if re.search(pat, t):
            return True
    return False


def fetch_weekly_market_events(take: int = 6) -> list[dict]:
    """Busca os principais acontecimentos da semana que movimentaram o mercado.

    Usa Apify com queries específicas de eventos semanais (Ibovespa fechou, balanços,
    decisões do Copom, resultados, etc.). Filtra títulos genéricos.
    Retorna [] se APIFY_TOKEN ausente ou falhar.
    """
    if not APIFY_TOKEN:
        return []
    print(f"📅 Apify: principais acontecimentos da semana...")
    # Queries focadas em manchetes reais de eventos semanais
    queries = [
        "Ibovespa fechou semana balanço alta queda esta semana",
        "Copom Selic Banco Central decisão impacto mercado esta semana",
        "ações destaques semana resultados balanço empresas Brasil",
        "fundos imobiliários FIIs semana destaque rendimento",
    ]
    all_events = []
    seen = set()
    for q in queries:
        results = fetch_apify_news(q, take=8)
        for item in results:
            title = item["title"]
            t_key = title.lower()[:60]
            if t_key in seen:
                continue
            if _is_generic_title(title):
                continue
            seen.add(t_key)
            all_events.append(item)
            if len(all_events) >= take * 2:
                break
        if len(all_events) >= take * 2:
            break
    return all_events[:take]


def fetch_apify_news(query: str, take: int = 8) -> list[dict]:
    """Busca notícias via Apify (apify/rag-web-browser — oficial, gratuito até créditos).

    Faz uma busca Google e retorna os top N resultados orgânicos. Retorna [] se
    APIFY_TOKEN ausente ou se a chamada falhar.
    """
    if not APIFY_TOKEN:
        return []
    print(f"🔎 Apify (rag-web-browser): '{query}'...")
    url = f"https://api.apify.com/v2/acts/apify~rag-web-browser/run-sync-get-dataset-items?token={APIFY_TOKEN}"
    payload = {
        "query": query,
        "maxResults": take,
        "outputFormats": ["markdown"],   # markdown leve com a página renderizada
        "scrapingTool": "raw-http",
    }
    try:
        r = requests.post(url, json=payload, timeout=180)
        r.raise_for_status()
        items = r.json()
        news = []
        seen = set()
        for item in items:
            sr = item.get("searchResult") or {}
            md = item.get("metadata") or {}
            title = (sr.get("title") or md.get("title") or "").strip()
            link = sr.get("url") or md.get("url") or ""
            description = (sr.get("description") or "").strip()
            if not title or not link or len(title) < 10:
                continue
            t_key = title.lower()[:60]
            if t_key in seen:
                continue
            seen.add(t_key)
            news.append({
                "title": title,
                "url": link,
                "source": f"Apify · {_domain_to_source(link)}",
                "date": "",
                "description": description[:200],
            })
            if len(news) >= take:
                break
        print(f"  → {len(news)} notícias retornadas pelo Apify (de {len(items)} brutas).")
        return news
    except requests.exceptions.HTTPError as e:
        body = ""
        try:
            body = e.response.text[:200]
        except Exception:
            pass
        print(f"  [WARN] Apify HTTP {e.response.status_code}: {body}")
        return []
    except Exception as e:
        print(f"  [WARN] Apify falhou: {e}")
        return []


def scrape_bom_dia_mercado() -> list[dict]:
    """Scrapa o Bom Dia Mercado."""
    print("📰 Scraping Bom Dia Mercado...")
    soup = _soup("https://www.bomdiamercado.com.br/")
    if not soup:
        return []
    news = []
    for article in soup.select("article, .post, [class*='card'], [class*='item']")[:8]:
        title_el = article.select_one("h2, h3, h4, a")
        link_el = article.select_one("a[href]")
        time_el = article.select_one("time, [class*='date']")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        href = link_el["href"] if link_el else "https://www.bomdiamercado.com.br/"
        if href.startswith("/"):
            href = "https://www.bomdiamercado.com.br" + href
        pub_date = time_el.get_text(strip=True) if time_el else ""
        if title and len(title) > 15:
            news.append({"title": title, "url": href, "source": "Bom Dia Mercado", "date": pub_date})
    return news[:5]


def scrape_einvestidor() -> list[dict]:
    """Scrapa o E-Investidor (Estadão)."""
    print("📰 Scraping E-Investidor...")
    soup = _soup("https://einvestidor.estadao.com.br/")
    if not soup:
        return []
    news = []
    for article in soup.select("article, .card, [class*='card'], [class*='post']")[:8]:
        title_el = article.select_one("h2, h3, h4, .headline")
        link_el = article.select_one("a[href]")
        time_el = article.select_one("time, [class*='date'], [class*='time']")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        href = link_el["href"] if link_el else "https://einvestidor.estadao.com.br/"
        if href.startswith("/"):
            href = "https://einvestidor.estadao.com.br" + href
        pub_date = time_el.get_text(strip=True) if time_el else ""
        if title and len(title) > 15:
            news.append({"title": title, "url": href, "source": "E-Investidor", "date": pub_date})
    return news[:5]


def scrape_valor_investe() -> list[dict]:
    """Scrapa o Valor Investe (Globo)."""
    print("📰 Scraping Valor Investe...")
    soup = _soup("https://valorinveste.globo.com/")
    if not soup:
        return []
    news = []
    for article in soup.select("article, .feed-post, [class*='post-card'], [class*='feed-item']")[:8]:
        title_el = article.select_one("h2, h3, [class*='headline'], [class*='title']")
        link_el = article.select_one("a[href]")
        time_el = article.select_one("time, [class*='date']")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        href = link_el["href"] if link_el else "https://valorinveste.globo.com/"
        if href.startswith("/"):
            href = "https://valorinveste.globo.com" + href
        pub_date = time_el.get_text(strip=True) if time_el else ""
        if title and len(title) > 15:
            news.append({"title": title, "url": href, "source": "Valor Investe", "date": pub_date})
    return news[:5]


def collect_all_news() -> tuple[list[dict], list[dict], list[dict]]:
    """Coleta notícias de todas as fontes.
    Retorna (morning_call_news, all_news, weekly_events)."""
    # Fontes diretas (HTML)
    bdm_news = scrape_bom_dia_mercado()
    mt_news = scrape_money_times()
    sd_news = scrape_seu_dinheiro()
    ei_news = scrape_einvestidor()
    vi_news = scrape_valor_investe()

    # Apify (premium — só roda se APIFY_TOKEN configurado)
    apify_market = fetch_apify_news("mercado financeiro Brasil hoje Ibovespa", take=8)
    apify_morning = fetch_apify_news("morning call mercado abertura bolsa hoje", take=5)
    weekly_events = fetch_weekly_market_events(take=6)

    # Morning Call: prioriza Apify; fallback para top headlines
    morning_call_news = apify_morning or (mt_news + bdm_news)[:5]

    all_news = []
    seen_titles = set()
    for item in (apify_market + bdm_news + mt_news + sd_news + ei_news + vi_news):
        t = item["title"].lower()[:60]
        if t not in seen_titles and len(item["title"]) > 15:
            seen_titles.add(t)
            all_news.append(item)

    print(f"  → {len(all_news)} notícias coletadas "
          f"(Apify={len(apify_market)}, BDM={len(bdm_news)}, "
          f"MT={len(mt_news)}, SD={len(sd_news)}, "
          f"EI={len(ei_news)}, VI={len(vi_news)}) | "
          f"Eventos da semana: {len(weekly_events)}")

    return morning_call_news, all_news[:15], weekly_events


# ---------------------------------------------------------------------------
# 3. Geração de análise com Claude
# ---------------------------------------------------------------------------

def _build_fallback_analysis(market_data: dict, morning_news: list[dict],
                              all_news: list[dict], weekly_events: list[dict]) -> dict:
    """Monta um resumo factual a partir das notícias e dados de mercado quando
    a IA não está disponível. Sem inventar nada — apenas headlines reais."""
    ibov = market_data["ibovespa"]
    dolar = market_data["dolar"]
    sp500 = market_data["sp500"]

    # Resumo executivo: combina dados de mercado + principais eventos da semana
    exec_bullets = []

    # Bullet 1: posição do Ibovespa hoje
    ibov_dir = "subiu" if ibov["change"] >= 0 else "caiu"
    exec_bullets.append(
        f"Ibovespa {ibov_dir} {abs(ibov['change']):.2f}% hoje, aos {ibov['price']:,.0f} pontos. "
        f"Dólar a R$ {dolar['price']:.4f} ({_sign(dolar['change'])}{dolar['change']:.2f}%). "
        f"S&P 500 {_sign(sp500['change'])}{sp500['change']:.2f}%."
    )

    # Bullets 2-6: principais eventos da semana (via Apify)
    for ev in weekly_events[:5]:
        title = ev["title"].rstrip(" .")
        src = ev.get("source", "").replace("Apify · ", "")
        if src and src != "Web":
            exec_bullets.append(f"{title} ({src})")
        else:
            exec_bullets.append(title)

    # Se sobrou pouca coisa do Apify, complementa com headlines gerais
    if len(exec_bullets) < 5:
        for n in all_news[:6]:
            if len(exec_bullets) >= 6:
                break
            title = n["title"].rstrip(" .")
            src = n.get("source", "").replace("Apify · ", "")
            line = f"{title} ({src})" if src else title
            if line not in exec_bullets:
                exec_bullets.append(line)

    # Morning call: usa as notícias do morning_news
    mc_bullets = []
    for n in morning_news[:4]:
        title = n["title"].rstrip(" .")
        src = n.get("source", "").replace("Apify · ", "")
        mc_bullets.append(f"{title} ({src})" if src else title)
    if not mc_bullets:
        mc_bullets = ["Morning Call sem cobertura no momento — veja as notícias na seção abaixo."]

    # Contexto macro: monta a partir de variações de índices globais
    macro = (
        f"Mercados externos: S&P 500 {_sign(sp500['change'])}{sp500['change']:.2f}%, "
        f"Nasdaq {_sign(market_data['nasdaq']['change'])}{market_data['nasdaq']['change']:.2f}%, "
        f"Bitcoin {_sign(market_data['bitcoin']['change'])}{market_data['bitcoin']['change']:.2f}%, "
        f"Brent {_sign(market_data['brent']['change'])}{market_data['brent']['change']:.2f}%."
    )

    # Resumo semanal: usa eventos da semana
    weekly = []
    for ev in weekly_events[:5]:
        title = ev["title"].rstrip(" .")
        src = ev.get("source", "").replace("Apify · ", "")
        weekly.append(f"{title} ({src})" if src else title)
    if not weekly:
        weekly = ["Configure APIFY_TOKEN no .env para ver os principais eventos da semana."]

    return {
        "executive_summary": exec_bullets[:6],
        "morning_call_bullets": mc_bullets,
        "macro_context": macro,
        "weekly_summary": weekly,
    }


def generate_ai_analysis(market_data: dict, morning_news: list[dict],
                         all_news: list[dict], weekly_events: list[dict] = None) -> dict:
    """Chama Claude API para gerar resumo executivo e morning call.

    Se a API key não estiver configurada, monta um resumo factual a partir das
    notícias reais coletadas (Apify + scrapers diretos).
    """
    weekly_events = weekly_events or []

    if not ANTHROPIC_API_KEY:
        print("  [INFO] ANTHROPIC_API_KEY não configurado — gerando resumo a partir das notícias coletadas.")
        return _build_fallback_analysis(market_data, morning_news, all_news, weekly_events)

    print("🤖 Gerando análise com Claude AI...")

    ibov = market_data["ibovespa"]
    dolar = market_data["dolar"]
    sp500 = market_data["sp500"]
    btc = market_data["bitcoin"]
    brent = market_data["brent"]

    mkt_summary = f"""
DADOS DE MERCADO (coletados agora):
- Ibovespa: {ibov['price']:,.0f} pts ({_sign(ibov['change'])}{ibov['change']:.2f}%)
- Dólar/Real: R$ {dolar['price']:.4f} ({_sign(dolar['change'])}{dolar['change']:.2f}%)
- S&P 500: {sp500['price']:,.2f} ({_sign(sp500['change'])}{sp500['change']:.2f}%)
- Bitcoin: $ {btc['price']:,.2f} ({_sign(btc['change'])}{btc['change']:.2f}%)
- Petróleo Brent: $ {brent['price']:.2f} ({_sign(brent['change'])}{brent['change']:.2f}%)
""".strip()

    highs_str = "\n".join(
        f"  - {h.get('stock', h.get('symbol','?'))}: +{h.get('change', h.get('regularMarketChangePercent', 0)):.2f}%"
        for h in market_data.get("top_highs", [])[:5]
    ) or "  - Dados indisponíveis"

    lows_str = "\n".join(
        f"  - {l.get('stock', l.get('symbol','?'))}: {l.get('change', l.get('regularMarketChangePercent', 0)):.2f}%"
        for l in market_data.get("top_lows", [])[:5]
    ) or "  - Dados indisponíveis"

    news_str = "\n".join(
        f"  [{n['source']}] {n['title']}"
        for n in all_news[:12]
    ) or "  - Sem notícias coletadas"

    morning_str = "\n".join(
        f"  - {n['title']}"
        for n in morning_news[:5]
    ) or "  - Morning Call indisponível"

    weekly_str = "\n".join(
        f"  - [{n.get('source','').replace('Apify · ','')}] {n['title']}"
        for n in weekly_events[:8]
    ) or "  - Sem eventos da semana coletados"

    prompt = f"""Você é um analista de mercado financeiro sênior brasileiro com 20 anos de experiência.
Com base nas seguintes informações coletadas AGORA ({datetime.now().strftime('%d/%m/%Y %H:%M')}), gere em português brasileiro:

{mkt_summary}

TOP ALTAS DO IBOVESPA HOJE:
{highs_str}

TOP BAIXAS DO IBOVESPA HOJE:
{lows_str}

NOTÍCIAS DAS ÚLTIMAS HORAS:
{news_str}

PRINCIPAIS ACONTECIMENTOS DA SEMANA (que mexeram com o mercado — bolsa, fundos, macro):
{weekly_str}

CONTEÚDO MORNING CALL DO MERCADO:
{morning_str}

Gere EXATAMENTE no formato JSON a seguir (sem markdown, sem texto antes ou depois):
{{
  "executive_summary": [
    "bullet 1 — PRINCIPAIS ACONTECIMENTOS DA SEMANA que mexeram com a bolsa/fundos (use os dados acima)",
    "bullet 2 — outro evento relevante da semana com impacto no mercado",
    "bullet 3 — movimento macro/setorial relevante da semana",
    "bullet 4 — destaque corporativo (resultados, M&A, etc.)",
    "bullet 5 — o que ficar de olho / agenda da próxima semana"
  ],
  "morning_call_bullets": [
    "bullet 1 do morning call sintético (foco no que move HOJE)",
    "bullet 2",
    "bullet 3",
    "bullet 4"
  ],
  "macro_context": "1 a 2 frases sobre o contexto macro global movendo os mercados hoje",
  "weekly_summary": [
    "principal movimento da semana 1 (números, %, cenário)",
    "principal movimento da semana 2",
    "principal movimento da semana 3"
  ]
}}

Seja direto, preciso e prático. Use dados reais fornecidos. Não invente números."""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        # Remove possível markdown code fence
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
        print("  → Análise IA gerada com sucesso.")
        return result
    except json.JSONDecodeError as e:
        print(f"  [WARN] JSON inválido da IA: {e}")
        return {
            "executive_summary": ["Erro ao processar resposta da IA — verifique os logs."],
            "morning_call_bullets": ["Erro ao processar morning call."],
            "macro_context": "Análise indisponível neste momento.",
            "weekly_summary": ["Resumo semanal indisponível."],
        }
    except Exception as e:
        print(f"  [WARN] Erro na API Claude: {e}")
        return {
            "executive_summary": [f"Erro na API Claude: {str(e)[:80]}"],
            "morning_call_bullets": ["Verifique sua ANTHROPIC_API_KEY no arquivo .env"],
            "macro_context": "Análise macroeconômica indisponível.",
            "weekly_summary": ["Resumo semanal indisponível."],
        }


# ---------------------------------------------------------------------------
# 4. Geração do HTML
# ---------------------------------------------------------------------------

SOURCE_COLORS = {
    "Money Times": "#f59e0b",
    "Bom Dia Mercado": "#00b4d8",
    "Seu Dinheiro": "#10b981",
    "E-Investidor": "#2d6a4f",
    "Valor Investe": "#7209b7",
}

SOURCE_BG = {
    "Money Times": "rgba(245,158,11,0.15)",
    "Bom Dia Mercado": "rgba(0,180,216,0.15)",
    "Seu Dinheiro": "rgba(16,185,129,0.15)",
    "E-Investidor": "rgba(45,106,79,0.15)",
    "Valor Investe": "rgba(114,9,183,0.15)",
}


def _source_color(src: str) -> tuple[str, str]:
    """Retorna (cor, fundo) para uma fonte, com handling para fontes Apify."""
    if src.startswith("Apify"):
        return "#a78bfa", "rgba(167,139,250,0.15)"
    return SOURCE_COLORS.get(src, "#6366f1"), SOURCE_BG.get(src, "rgba(99,102,241,0.15)")

WEEKDAYS_PT = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
               "Sexta-feira", "Sábado", "Domingo"]
MONTHS_PT = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
             "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


def _date_label(dt: datetime) -> str:
    wd = WEEKDAYS_PT[dt.weekday()]
    mo = MONTHS_PT[dt.month - 1]
    return f"{wd}, {dt.day:02d} de {mo} de {dt.year} — {dt.strftime('%H:%M')}"


def _kpi_card(label: str, price_str: str, change: float, icon: str, unit: str = "") -> str:
    color = "#22c55e" if change >= 0 else "#ef4444"
    arrow = "▲" if change >= 0 else "▼"
    sign = "+" if change >= 0 else ""
    bar_w = min(abs(change) * 5, 100)
    bar_color = color
    return f"""
    <div class="kpi-card">
      <div class="kpi-icon">{icon}</div>
      <div class="kpi-label">{label}</div>
      <div class="kpi-price">{unit}{price_str}</div>
      <div class="kpi-change" style="color:{color}">
        {arrow} {sign}{change:.2f}%
      </div>
      <div class="kpi-bar-track">
        <div class="kpi-bar-fill" style="width:{bar_w}%;background:{bar_color}"></div>
      </div>
    </div>"""


def _mover_row(rank: int, item: dict, is_high: bool) -> str:
    sym = item.get("stock") or item.get("symbol") or "?"
    name = item.get("name") or item.get("shortName") or sym
    chg = float(item.get("change") or item.get("regularMarketChangePercent") or 0)
    price = float(item.get("price") or item.get("regularMarketPrice") or 0)
    currency = item.get("currency", "BRL")
    color = "#22c55e" if is_high else "#ef4444"
    sign = "+" if is_high else ""
    bar_w = min(abs(chg) * 8, 100)
    name_short = name[:22] + "…" if len(name) > 22 else name
    if price:
        price_fmt = f"R$ {price:.2f}" if currency == "BRL" else f"$ {price:.2f}"
    else:
        price_fmt = ""
    return f"""
      <div class="mover-row">
        <span class="mover-rank">#{rank}</span>
        <div class="mover-info">
          <span class="mover-ticker">{sym}</span>
          <span class="mover-name">{name_short}</span>
          {f'<span class="mover-price">{price_fmt}</span>' if price_fmt else ''}
        </div>
        <div class="mover-right">
          <span class="mover-pct" style="color:{color}">{sign}{chg:.2f}%</span>
          <div class="mover-bar-track">
            <div class="mover-bar" style="width:{bar_w}%;background:{color}"></div>
          </div>
        </div>
      </div>"""


def _news_card(n: dict) -> str:
    src = n.get("source", "Notícia")
    color, bg = _source_color(src)
    title = n.get("title", "Sem título")[:120]
    url = n.get("url", "#")
    date = n.get("date", "")
    return f"""
    <a class="news-card" href="{url}" target="_blank" rel="noopener">
      <div class="news-source-badge" style="color:{color};background:{bg}">{src}</div>
      <div class="news-title">{title}</div>
      {f'<div class="news-date">🕐 {date}</div>' if date else ''}
      <div class="news-arrow">Ler matéria →</div>
    </a>"""


def generate_html(market: dict, morning_news: list[dict], all_news: list[dict], ai: dict) -> str:
    now = datetime.now()
    date_str = _date_label(now)
    next_update = (now.replace(hour=7, minute=0, second=0) + timedelta(days=1)).strftime("%d/%m/%Y às 07:00")

    # KPIs
    ibov = market["ibovespa"]
    dolar = market["dolar"]
    sp500 = market["sp500"]
    btc = market["bitcoin"]
    brent = market["brent"]
    gold = market["gold"]
    nasdaq = market["nasdaq"]

    kpi_ibov = _kpi_card("Ibovespa", f"{ibov['price']:,.0f}", ibov["change"], "📈", "")
    kpi_dolar = _kpi_card("Dólar / Real", f"{dolar['price']:.4f}", dolar["change"], "💵", "R$ ")
    kpi_sp500 = _kpi_card("S&P 500", f"{sp500['price']:,.2f}", sp500["change"], "🇺🇸", "")
    kpi_btc = _kpi_card("Bitcoin", f"{btc['price']:,.0f}", btc["change"], "₿", "$ ")
    kpi_brent = _kpi_card("Petróleo Brent", f"{brent['price']:.2f}", brent["change"], "🛢️", "$ ")
    kpi_gold = _kpi_card("Ouro", f"{gold['price']:,.2f}", gold["change"], "🥇", "$ ")

    # AI bullets
    exec_bullets = "".join(
        f'<li class="ai-bullet"><span class="bullet-dot">◆</span>{b}</li>'
        for b in ai.get("executive_summary", [])
    )
    mc_bullets = "".join(
        f'<li class="mc-bullet"><span class="bullet-dot">▸</span>{b}</li>'
        for b in ai.get("morning_call_bullets", [])
    )
    macro_ctx = ai.get("macro_context", "")
    weekly_bullets = "".join(
        f'<li class="weekly-bullet">{b}</li>'
        for b in ai.get("weekly_summary", [])
    )

    # Global movers
    _na = '<p style="color:#555;padding:1rem">Dados indisponíveis</p>'
    global_highs_rows = "".join(
        _mover_row(i + 1, h, True)
        for i, h in enumerate(market.get("global_highs", [])[:5])
    ) or _na
    global_lows_rows = "".join(
        _mover_row(i + 1, l, False)
        for i, l in enumerate(market.get("global_lows", [])[:5])
    ) or _na

    # BR blue chips
    br_highs_rows = "".join(
        _mover_row(i + 1, h, True)
        for i, h in enumerate(market.get("br_main_highs", [])[:5])
    ) or _na
    br_lows_rows = "".join(
        _mover_row(i + 1, l, False)
        for i, l in enumerate(market.get("br_main_lows", [])[:5])
    ) or _na

    # News cards
    news_cards = "".join(_news_card(n) for n in all_news[:15])
    if not news_cards:
        news_cards = '<p style="color:#555;grid-column:1/-1;padding:2rem">Nenhuma notícia coletada.</p>'

    morning_url = morning_news[0]["url"] if morning_news else "https://www.moneytimes.com.br/ultimas-noticias/"
    morning_source = morning_news[0]["source"] if morning_news else "Mercado"
    has_api = "✅ Análise IA ativa" if ANTHROPIC_API_KEY else "⚠️ IA desabilitada (configure .env)"
    has_apify = "🔎 Apify ativo" if APIFY_TOKEN else "🔎 Apify desabilitado"

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>📊 Briefing Matinal — Mercado Financeiro</title>
<style>
:root {{
  --bg: #0a0a0f;
  --card: #12121a;
  --card2: #1a1a26;
  --border: #1e1e2e;
  --text: #e2e8f0;
  --muted: #64748b;
  --green: #22c55e;
  --red: #ef4444;
  --blue: #3b82f6;
  --purple: #8b5cf6;
  --orange: #f97316;
  --accent-grad: linear-gradient(135deg,#1d4ed8 0%,#0ea5e9 50%,#06b6d4 100%);
  --gold-grad: linear-gradient(135deg,#d97706 0%,#f59e0b 100%);
  --radius: 14px;
  --shadow: 0 4px 24px rgba(0,0,0,0.5);
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:'Inter','Segoe UI',system-ui,sans-serif;min-height:100vh;line-height:1.6}}
a{{color:inherit;text-decoration:none}}

/* LAYOUT */
.container{{max-width:1400px;margin:0 auto;padding:1.5rem 1.2rem}}
.section{{margin-bottom:2rem}}
.section-title{{font-size:1rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:1rem;display:flex;align-items:center;gap:.5rem}}
.section-title::after{{content:'';flex:1;height:1px;background:var(--border)}}

/* HEADER */
.header{{
  background:linear-gradient(135deg,#0f0f1a 0%,#12121f 60%,#0a0a14 100%);
  border:1px solid var(--border);border-radius:var(--radius);
  padding:2rem 2.5rem;margin-bottom:2rem;
  display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:1rem;
  box-shadow:var(--shadow);
  position:relative;overflow:hidden;
}}
.header::before{{
  content:'';position:absolute;top:-60px;right:-60px;
  width:220px;height:220px;border-radius:50%;
  background:radial-gradient(circle,rgba(59,130,246,.12) 0%,transparent 70%);
}}
.header-left h1{{font-size:1.8rem;font-weight:800;background:var(--accent-grad);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
.header-left .subtitle{{color:var(--muted);font-size:.9rem;margin-top:.25rem}}
.header-right{{display:flex;flex-direction:column;align-items:flex-end;gap:.5rem}}
.badge-updated{{background:rgba(34,197,94,.15);border:1px solid rgba(34,197,94,.3);color:var(--green);padding:.3rem .8rem;border-radius:999px;font-size:.75rem;font-weight:600;animation:pulse 2s infinite}}
.badge-ai{{font-size:.7rem;color:var(--muted)}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.6}}}}

/* KPI GRID */
.kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1rem}}
.kpi-card{{
  background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  padding:1.2rem 1rem;transition:transform .2s,border-color .2s;cursor:default;
}}
.kpi-card:hover{{transform:translateY(-3px);border-color:#2e2e42}}
.kpi-icon{{font-size:1.5rem;margin-bottom:.4rem}}
.kpi-label{{font-size:.7rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600}}
.kpi-price{{font-size:1.35rem;font-weight:800;margin:.25rem 0;font-variant-numeric:tabular-nums}}
.kpi-change{{font-size:.85rem;font-weight:700;margin-bottom:.5rem}}
.kpi-bar-track{{height:3px;background:#1e1e2e;border-radius:99px;overflow:hidden}}
.kpi-bar-fill{{height:100%;border-radius:99px;transition:width .8s ease}}

/* AI SUMMARY */
.ai-card{{
  background:linear-gradient(135deg,rgba(59,130,246,.08) 0%,rgba(139,92,246,.08) 100%);
  border:1px solid rgba(99,102,241,.25);border-radius:var(--radius);padding:1.8rem 2rem;
}}
.ai-card-title{{font-size:1.1rem;font-weight:700;margin-bottom:1rem;display:flex;align-items:center;gap:.5rem}}
.ai-tag{{font-size:.65rem;background:rgba(139,92,246,.2);border:1px solid rgba(139,92,246,.4);color:#a78bfa;padding:.2rem .5rem;border-radius:999px;font-weight:600}}
.ai-bullet{{list-style:none;padding:.45rem 0;border-bottom:1px solid rgba(255,255,255,.05);display:flex;align-items:flex-start;gap:.7rem;font-size:.92rem}}
.ai-bullet:last-child{{border-bottom:none}}
.bullet-dot{{color:#6366f1;font-size:.8rem;margin-top:.25rem;flex-shrink:0}}

/* MORNING CALL */
.mc-card{{
  background:linear-gradient(135deg,rgba(255,107,0,.08) 0%,rgba(249,115,22,.05) 100%);
  border:1px solid rgba(255,107,0,.2);border-radius:var(--radius);padding:1.8rem 2rem;
}}
.mc-header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem;flex-wrap:wrap;gap:.5rem}}
.mc-badge{{background:rgba(255,107,0,.2);border:1px solid rgba(255,107,0,.4);color:#fb923c;padding:.3rem .8rem;border-radius:999px;font-size:.75rem;font-weight:700;letter-spacing:.05em}}
.mc-link{{font-size:.8rem;color:#60a5fa;opacity:.8;transition:opacity .2s}}
.mc-link:hover{{opacity:1}}
.mc-bullet{{list-style:none;padding:.4rem 0;border-bottom:1px solid rgba(255,255,255,.04);display:flex;gap:.7rem;font-size:.92rem;align-items:flex-start}}
.mc-bullet:last-child{{border-bottom:none}}
.mc-bullet .bullet-dot{{color:#f97316}}

/* MACRO */
.macro-card{{
  background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  padding:1.4rem 1.8rem;margin-top:1rem;font-size:.9rem;color:#94a3b8;font-style:italic;
}}

/* MOVERS */
.movers-grid{{display:grid;grid-template-columns:1fr 1fr;gap:1rem}}
@media(max-width:640px){{.movers-grid{{grid-template-columns:1fr}}}}
.movers-col{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:1.2rem}}
.movers-col-title{{font-size:.85rem;font-weight:700;margin-bottom:.8rem;display:flex;align-items:center;gap:.4rem}}
.mover-row{{display:flex;align-items:center;gap:.7rem;padding:.5rem 0;border-bottom:1px solid rgba(255,255,255,.04)}}
.mover-row:last-child{{border-bottom:none}}
.mover-rank{{color:var(--muted);font-size:.7rem;font-weight:700;width:1.2rem;text-align:center;flex-shrink:0}}
.mover-info{{flex:1;min-width:0}}
.mover-ticker{{font-weight:800;font-size:.85rem;margin-right:.4rem}}
.mover-name{{font-size:.72rem;color:var(--muted);display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.mover-price{{font-size:.7rem;color:#475569}}
.mover-right{{text-align:right;min-width:70px}}
.mover-pct{{font-weight:700;font-size:.85rem;display:block}}
.mover-bar-track{{height:3px;background:#1e1e2e;border-radius:99px;margin-top:.3rem;overflow:hidden}}
.mover-bar{{height:100%;border-radius:99px}}
.movers-panel-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:.8rem}}
.movers-panel-header .movers-col-title{{margin-bottom:0}}
.movers-panel-status{{font-size:.68rem;padding:.2rem .55rem;border-radius:999px;background:rgba(255,255,255,.06);color:var(--muted);white-space:nowrap}}
.movers-sub-label{{font-size:.78rem;font-weight:700;padding:.35rem 0;margin:.4rem 0 .2rem;display:flex;align-items:center;gap:.35rem}}
.movers-sub-divider{{height:1px;background:var(--border);margin:.55rem 0}}
.movers-updated{{font-size:.63rem;color:var(--muted);text-align:right;margin-top:.4rem}}

/* NEWS GRID */
.news-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:1rem}}
.news-card{{
  background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  padding:1.2rem;display:flex;flex-direction:column;gap:.5rem;
  transition:transform .2s,border-color .2s;
}}
.news-card:hover{{transform:translateY(-2px);border-color:#2e2e42}}
.news-source-badge{{display:inline-block;font-size:.7rem;font-weight:700;padding:.25rem .6rem;border-radius:999px;letter-spacing:.04em;width:fit-content}}
.news-title{{font-size:.88rem;font-weight:600;line-height:1.4;flex:1}}
.news-date{{font-size:.72rem;color:var(--muted)}}
.news-arrow{{font-size:.75rem;color:#3b82f6;margin-top:.2rem}}

/* WEEKLY COLLAPSE */
.weekly-card{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}}
.weekly-toggle{{
  width:100%;background:none;border:none;color:var(--text);cursor:pointer;
  padding:1.2rem 1.5rem;display:flex;justify-content:space-between;align-items:center;
  font-size:.95rem;font-weight:600;transition:background .2s;
}}
.weekly-toggle:hover{{background:rgba(255,255,255,.03)}}
.weekly-toggle-icon{{transition:transform .3s;color:var(--muted)}}
.weekly-toggle.open .weekly-toggle-icon{{transform:rotate(180deg)}}
.weekly-body{{display:none;padding:0 1.5rem 1.2rem}}
.weekly-body.open{{display:block}}
.weekly-bullet{{list-style:none;padding:.4rem 0;border-bottom:1px solid rgba(255,255,255,.04);font-size:.88rem;padding-left:1rem;position:relative}}
.weekly-bullet::before{{content:'•';position:absolute;left:0;color:#6366f1}}
.weekly-bullet:last-child{{border-bottom:none}}

/* FOOTER */
.footer{{
  background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  padding:1.5rem 2rem;margin-top:2rem;
}}
.footer-top{{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:1rem}}
.footer-sources a{{color:#60a5fa;font-size:.8rem;display:block;margin:.15rem 0}}
.footer-disclaimer{{font-size:.75rem;color:var(--muted);max-width:500px;line-height:1.5}}
.footer-bottom{{margin-top:1rem;padding-top:1rem;border-top:1px solid var(--border);font-size:.75rem;color:var(--muted);display:flex;justify-content:space-between;flex-wrap:wrap;gap:.5rem}}

/* UTIL */
.green{{color:var(--green)}}
.red{{color:var(--red)}}
.divider-two{{display:grid;grid-template-columns:1fr 1fr;gap:1rem}}
@media(max-width:768px){{.divider-two{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="container">

  <!-- HEADER -->
  <div class="header">
    <div class="header-left">
      <h1>📊 Briefing Matinal — Mercado Financeiro</h1>
      <div class="subtitle">{date_str}</div>
    </div>
    <div class="header-right">
      <div class="badge-updated">● Atualizado agora</div>
      <div class="badge-ai">{has_api} · {has_apify}</div>
    </div>
  </div>

  <!-- SEÇÃO 1 — KPIs -->
  <div class="section">
    <div class="section-title">📡 Mercado em Tempo Real</div>
    <div class="kpi-grid">
      {kpi_ibov}
      {kpi_dolar}
      {kpi_sp500}
      {kpi_btc}
      {kpi_brent}
      {kpi_gold}
    </div>
  </div>

  <!-- SEÇÃO 2 e 3 lado a lado -->
  <div class="divider-two">

    <!-- SEÇÃO 2 — O que mexeu com o mercado -->
    <div class="section">
      <div class="section-title">🧠 O que o investidor precisa saber {'<span class="ai-tag">IA</span>' if ANTHROPIC_API_KEY else '<span class="ai-tag" style="background:rgba(34,197,94,.2);border-color:rgba(34,197,94,.4);color:#4ade80">Notícias reais</span>'}</div>
      <div class="ai-card">
        <div class="ai-card-title">
          Principais acontecimentos da semana que mexeram com o mercado
          <span class="ai-tag">{'Análise por IA' if ANTHROPIC_API_KEY else 'Headlines reais'}</span>
        </div>
        <ul>{exec_bullets}</ul>
      </div>
      {f'<div class="macro-card"><strong>🌍 Contexto Macro:</strong> {macro_ctx}</div>' if macro_ctx else ''}
    </div>

    <!-- SEÇÃO 3 — Morning Call do Mercado -->
    <div class="section">
      <div class="section-title">☀️ Morning Call do Mercado</div>
      <div class="mc-card">
        <div class="mc-header">
          <span class="mc-badge">Abertura · {morning_source}</span>
          <a class="mc-link" href="{morning_url}" target="_blank" rel="noopener">Ver matéria original →</a>
        </div>
        <ul>{mc_bullets}</ul>
      </div>
    </div>

  </div>

  <!-- SEÇÃO 4 — Rankings -->
  <div class="section">
    <div class="section-title">🏆 Rankings de Mercado — Altas &amp; Baixas do Dia</div>
    <div class="movers-grid">

      <!-- ESQUERDO: Ações Globais -->
      <div class="movers-col">
        <div class="movers-panel-header">
          <div class="movers-col-title">🌍 Ações Globais</div>
          <span class="movers-panel-status" id="global-status">⏳ Carregando…</span>
        </div>
        <div class="movers-sub-label"><span class="green">▲</span> Top 5 Altas</div>
        <div id="global-highs">{global_highs_rows}</div>
        <div class="movers-sub-divider"></div>
        <div class="movers-sub-label"><span class="red">▼</span> Top 5 Baixas</div>
        <div id="global-lows">{global_lows_rows}</div>
        <div class="movers-updated" id="global-updated"></div>
      </div>

      <!-- DIREITO: Principais Blue Chips B3 -->
      <div class="movers-col">
        <div class="movers-panel-header">
          <div class="movers-col-title">🇧🇷 Principais B3</div>
          <span class="movers-panel-status" id="br-status">⏳ Carregando…</span>
        </div>
        <div class="movers-sub-label"><span class="green">▲</span> Top 5 Altas</div>
        <div id="br-highs">{br_highs_rows}</div>
        <div class="movers-sub-divider"></div>
        <div class="movers-sub-label"><span class="red">▼</span> Top 5 Baixas</div>
        <div id="br-lows">{br_lows_rows}</div>
        <div class="movers-updated" id="br-updated"></div>
      </div>

    </div>
  </div>

  <!-- SEÇÃO 5 — Notícias -->
  <div class="section">
    <div class="section-title">📰 Notícias em Destaque — Últimas 24h</div>
    <div class="news-grid">
      {news_cards}
    </div>
  </div>

  <!-- SEÇÃO 6 — Resumo Semanal (colapsável) -->
  <div class="section">
    <div class="section-title">📅 Resumo Semanal</div>
    <div class="weekly-card">
      <button class="weekly-toggle" onclick="toggleWeekly(this)">
        <span>Principais movimentos dos últimos 7 dias</span>
        <span class="weekly-toggle-icon">▼</span>
      </button>
      <div class="weekly-body" id="weeklyBody">
        <ul>{weekly_bullets}</ul>
      </div>
    </div>
  </div>

  <!-- FOOTER -->
  <div class="footer">
    <div class="footer-top">
      <div class="footer-sources">
        <strong style="font-size:.8rem">Fontes:</strong>
        <a href="https://www.moneytimes.com.br/" target="_blank">Money Times</a>
        <a href="https://www.seudinheiro.com/" target="_blank">Seu Dinheiro</a>
        <a href="https://www.bomdiamercado.com.br/" target="_blank">Bom Dia Mercado</a>
        <a href="https://einvestidor.estadao.com.br/" target="_blank">E-Investidor (Estadão)</a>
        <a href="https://valorinveste.globo.com/" target="_blank">Valor Investe (Globo)</a>
        <a href="https://apify.com/apify/rag-web-browser" target="_blank">Apify · RAG Web Browser (premium)</a>
        <a href="https://brapi.dev/" target="_blank">brapi.dev (Top Movers Ibovespa)</a>
        <a href="https://finance.yahoo.com/" target="_blank">Yahoo Finance (índices)</a>
      </div>
      <div class="footer-disclaimer">
        ⚠️ Este dashboard é meramente informativo e gerado automaticamente.
        <strong>Não constitui recomendação de investimento.</strong>
        Consulte sempre um assessor financeiro certificado antes de tomar decisões de investimento.
      </div>
    </div>
    <div class="footer-bottom">
      <span>Gerado em {now.strftime('%d/%m/%Y às %H:%M:%S')} · Dashboard Financeiro Matinal v1.0</span>
      <span>⏰ Próxima atualização sugerida: {next_update}</span>
    </div>
  </div>

</div>
<script>
var BRAPI_TOKEN_RT="{BRAPI_TOKEN}";
var BR_CHIPS={json.dumps(BR_BLUE_CHIPS)};
var GLOBAL_NAMES={json.dumps(GLOBAL_STOCKS_MAP)};

function isBROpen(){{
  var now=new Date(),brt=new Date(now.getTime()-3*3600*1000);
  var d=brt.getDay(),h=brt.getHours(),m=brt.getMinutes();
  return d>=1&&d<=5&&(h*60+m)>=600&&(h*60+m)<1075;
}}
function isNYSEOpen(){{
  var now=new Date(),et=new Date(now.getTime()-4*3600*1000);
  var d=et.getDay(),h=et.getHours(),m=et.getMinutes();
  return d>=1&&d<=5&&(h*60+m)>=570&&(h*60+m)<960;
}}
function mkRow(rank,item,isHigh){{
  var color=isHigh?'#22c55e':'#ef4444';
  var sign=isHigh?'+':'';
  var bw=Math.min(Math.abs(item.change)*8,100);
  var name=item.name&&item.name.length>22?item.name.slice(0,22)+'…':(item.name||item.stock);
  var pref=item.currency==='BRL'?'R$ ':'$ ';
  var priceStr=item.price?pref+item.price.toFixed(2):'';
  return '<div class="mover-row">'
    +'<span class="mover-rank">#'+rank+'</span>'
    +'<div class="mover-info">'
    +'<span class="mover-ticker">'+item.stock+'</span>'
    +'<span class="mover-name">'+name+'</span>'
    +(priceStr?'<span class="mover-price">'+priceStr+'</span>':'')
    +'</div>'
    +'<div class="mover-right">'
    +'<span class="mover-pct" style="color:'+color+'">'+sign+item.change.toFixed(2)+'%</span>'
    +'<div class="mover-bar-track"><div class="mover-bar" style="width:'+bw+'%;background:'+color+'"></div></div>'
    +'</div></div>';
}}
function setRows(elId,items,isHigh){{
  var el=document.getElementById(elId);
  if(el&&items&&items.length)el.innerHTML=items.map(function(x,i){{return mkRow(i+1,x,isHigh);}}).join('');
}}
async function loadBR(){{
  var chips=BR_CHIPS.join(',');
  var url='https://brapi.dev/api/quote/'+chips+'?fundamental=false'+(BRAPI_TOKEN_RT?'&token='+BRAPI_TOKEN_RT:'');
  try{{
    var r=await fetch(url);
    var d=await r.json();
    var items=(d.results||[]).filter(function(q){{return q.regularMarketPrice>0;}}).map(function(q){{
      return {{stock:q.symbol,name:q.shortName||q.symbol,change:q.regularMarketChangePercent||0,price:q.regularMarketPrice||0,currency:'BRL'}};
    }}).sort(function(a,b){{return b.change-a.change;}});
    setRows('br-highs',items.slice(0,5),true);
    setRows('br-lows',items.slice(-5).reverse(),false);
    var st=document.getElementById('br-status');
    if(st)st.textContent=isBROpen()?'🟢 Mercado aberto':'⚪️ Últ. pregão';
    var upd=document.getElementById('br-updated');
    if(upd)upd.textContent='Atualizado: '+new Date().toLocaleTimeString('pt-BR');
  }}catch(e){{console.warn('BR fetch error',e);}}
}}
async function loadGlobal(){{
  var syms=Object.keys(GLOBAL_NAMES).join(',');
  var url='https://query2.finance.yahoo.com/v7/finance/quote?symbols='+encodeURIComponent(syms);
  try{{
    var r=await fetch(url,{{headers:{{'Accept':'application/json'}}}});
    var d=await r.json();
    var items=(((d||{{}}).quoteResponse||{{}}).result||[]).filter(function(q){{return q.regularMarketPrice>0;}}).map(function(q){{
      return {{stock:q.symbol,name:GLOBAL_NAMES[q.symbol]||q.shortName||q.symbol,change:q.regularMarketChangePercent||0,price:q.regularMarketPrice||0,currency:'USD'}};
    }}).sort(function(a,b){{return b.change-a.change;}});
    if(items.length){{
      setRows('global-highs',items.slice(0,5),true);
      setRows('global-lows',items.slice(-5).reverse(),false);
      var st=document.getElementById('global-status');
      if(st)st.textContent=isNYSEOpen()?'🟢 Mercado aberto':'⚪️ Últ. pregão';
      var upd=document.getElementById('global-updated');
      if(upd)upd.textContent='Atualizado: '+new Date().toLocaleTimeString('pt-BR');
    }}
  }}catch(e){{console.warn('Global fetch failed (CORS?)',e);}}
}}
function refreshAll(){{loadBR();loadGlobal();}}
refreshAll();
setInterval(refreshAll,60000);
function toggleWeekly(btn){{
  btn.classList.toggle('open');
  var body=document.getElementById('weeklyBody');
  body.classList.toggle('open');
}}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 5. Orquestrador principal
# ---------------------------------------------------------------------------

def run():
    print("\n" + "=" * 60)
    print("  📊 DASHBOARD DIÁRIO DE MERCADO FINANCEIRO")
    print(f"  {_date_label(datetime.now())}")
    print("=" * 60 + "\n")

    # Coleta paralela (sequencial por simplicidade e para evitar ban de IP)
    market = fetch_market_data()
    print()
    morning_news, all_news, weekly_events = collect_all_news()
    print()
    ai = generate_ai_analysis(market, morning_news, all_news, weekly_events)
    print()

    # Gera HTML
    print("🎨 Gerando dashboard HTML...")
    html = generate_html(market, morning_news, all_news, ai)

    # Salva arquivo
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_file = OUTPUT_DIR / f"dashboard_{timestamp}.html"
    latest_file = OUTPUT_DIR / "dashboard_latest.html"

    out_file.write_text(html, encoding="utf-8")
    latest_file.write_text(html, encoding="utf-8")

    print(f"  → Salvo em: {out_file}")
    print(f"  → Atalho:   {latest_file}")

    # Abre no browser
    print("\n🌐 Abrindo no browser...")
    webbrowser.open(latest_file.as_uri())

    print("\n✅ Dashboard gerado com sucesso!\n")
    return str(latest_file)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n\nInterrompido pelo usuário.")
        sys.exit(0)
    except Exception:
        print("\n❌ Erro inesperado:")
        traceback.print_exc()
        sys.exit(1)
