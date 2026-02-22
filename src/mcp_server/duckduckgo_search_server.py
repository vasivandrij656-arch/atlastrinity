import html
import json
import logging
import os
import re
from typing import Any, cast

import requests
from mcp.server import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [SEARCH-SERVER] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8",
)
logger = logging.getLogger(__name__)

server = FastMCP("search-server")

# Path to protocol file (centralized configuration)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROTOCOL_PATH = os.path.join(
    PROJECT_ROOT, "src", "brain", "mcp", "data", "protocols", "search_protocol.txt"
)


def _load_protocol_config() -> dict[str, Any]:
    """Load configuration from the machine-readable section of the search protocol."""
    try:
        if not os.path.exists(PROTOCOL_PATH):
            return {}
        with open(PROTOCOL_PATH, encoding="utf-8") as f:
            content = f.read()

        # Find JSON block (starts after 9. MACHINE-READABLE CONFIGURATION)
        json_start = content.find("9. MACHINE-READABLE CONFIGURATION")
        if json_start != -1:
            match = re.search(r"\{.*\}", content[json_start:], re.DOTALL)
            if match:
                config = json.loads(match.group(0))
                return cast("dict[str, Any]", config)
    except Exception as e:
        logger.error(f"Error loading protocol: {e}")
    return {}


def _execute_protocol_search(rule_name: str, query_val: str, provider_name: str) -> dict[str, Any]:
    """Execute search based on rules defined in the protocol, with tiered temporal support."""
    config = _load_protocol_config()
    rules = config.get("search_rules", {})
    horizon = config.get("temporal_horizon", {})

    rule = rules.get(rule_name, {})
    operator = rule.get("operator", "{query}")
    priority_domains = rule.get("priority_domains", [])

    # Expand template
    expanded_query = operator.replace("{query}", query_val.strip())

    try:
        results = _search_ddg(query=expanded_query, max_results=10, timeout_s=15.0)

        # Tiered Deepening if insufficient results and it's a structural rule
        if len(results) < 3 and rule_name in ["open_data", "structured_data", "court"]:
            primary_years = horizon.get("primary_range", [2024, 2026])
            deep_years = horizon.get("deep_range", [2020, 2023])

            logger.info("Insufficient results for primary query. Initiating tiered deepening.")

            # Deepen to primary range first (if not already covered)
            for year in range(primary_years[1], primary_years[0] - 1, -1):
                year_query = f"{query_val.strip()} {year}"
                logger.info(f"Deepening search for year: {year}")
                results += _search_ddg(query=year_query, max_results=5, timeout_s=10.0)
                if len(results) >= 10:
                    break

            # If still low, go to deep range
            if len(results) < 5:
                for year in range(deep_years[1], deep_years[0] - 1, -1):
                    year_query = f"{query_val.strip()} {year}"
                    logger.info(f"Deepening search for year (deep): {year}")
                    results += _search_ddg(query=year_query, max_results=5, timeout_s=10.0)
                    if len(results) >= 10:
                        break

        prioritized = []
        others = []
        seen_urls = set()

        for r in results:
            if r["url"] in seen_urls:
                continue
            seen_urls.add(r["url"])
            if any(domain in r["url"] for domain in priority_domains):
                prioritized.append(r)
            else:
                others.append(r)

        # Semantic Echo (The Living Note)
        seeds = set()
        curiosity_config = config.get("organic_curiosity", {})
        anchors = curiosity_config.get("semantic_anchors", [])
        
        # Simple regex-based anchor detection in snippets
        for r in prioritized + others:
            text = f"{r['title']} {r.get('snippet', '')}"
            # Let's detect some common Ukrainian patterns if not explicitly in anchors
            # ЄДРПОУ (8 digits)
            edrpou_match = re.search(r"\b\d{8}\b", text)
            if edrpou_match:
                seeds.add(f"ЄДРПОУ: {edrpou_match.group(0)}")
            
            # Court Case No (e.g. 757/12345/21-ц)
            case_match = re.search(r"\b\d{3}/\d+/\d+[-а-яієґ]*\b", text)
            if case_match:
                seeds.add(f"No справи: {case_match.group(0)}")
                
            # Generic anchors from config
            for anchor in anchors:
                if anchor in text and anchor not in query_val:
                    # Try to extract the value after the anchor
                    pattern = re.escape(anchor) + r"[:\s]*([^\s,;)]+)"
                    val_match = re.search(pattern, text)
                    if val_match:
                        seeds.add(f"{anchor}: {val_match.group(1)}")

        return {
            "success": True,
            "query": expanded_query,
            "results": prioritized + others,
            "provider": provider_name,
            "temporal_horizon": horizon,
            "semantic_echoes": sorted(list(seeds)) if seeds else [],
            "curiosity_note": curiosity_config.get("behavior_note", "")
        }
    except Exception as e:
        return {"error": str(e)}


def _extract_from_match(match, seen_urls, results, max_results, is_fallback=False):
    """Extracted logic to process a single regex match."""
    href = html.unescape(match.group(1)).strip()

    # Filter DDG internal links
    forbidden = ["duckduckgo.com/", "ad_redirect", "javascript:"]
    if not is_fallback:
        forbidden.append("#")

    if any(x in href for x in forbidden):
        if "duckduckgo.com/l/?uddg=" not in href and "uddg=" not in href:
            return False

    # Title extraction
    if not is_fallback:
        title = html.unescape(match.group(2)).strip()
    else:
        title_html = match.group(2)
        title = html.unescape(re.sub(r"<.*?>", "", title_html)).strip()

    if not href or not title or len(title) < 2:
        return False

    # Clean up DDG redirects
    if "uddg=" in href:
        match_real = re.search(r"uddg=([^&]+)", href)
        if match_real:
            from urllib.parse import unquote

            href = unquote(match_real.group(1))

    if href.startswith("//"):
        href = "https:" + href
    elif is_fallback and href.startswith("/"):
        href = "https://duckduckgo.com" + href

    if is_fallback:
        # Filter UI elements
        if any(title.lower() == x for x in ["next", "previous", "images", "videos", "news"]):
            return False

    if href not in seen_urls and href.startswith("http"):
        seen_urls.add(href)
        results.append({"title": title, "url": href})
        return len(results) >= max_results
    return False


def _search_ddg(query: str, max_results: int, timeout_s: float) -> list[dict[str, Any]]:
    url = "https://html.duckduckgo.com/html/"
    try:
        resp = requests.post(
            url,
            data={"q": query},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://duckduckgo.com/",
                "Origin": "https://duckduckgo.com",
            },
            timeout=timeout_s,
        )
        resp.raise_for_status()
        if (
            not resp.text.strip()
            or "Checking your browser" in resp.text
            or "Cloudflare" in resp.text
        ):
            return []
    except Exception as e:
        logger.error(f"Request error: {e}")
        return []

    results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    # Method 1: Extraction via result__a class
    title_pattern = re.compile(r'class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)', re.IGNORECASE)
    for match in title_pattern.finditer(resp.text):
        if _extract_from_match(match, seen_urls, results, max_results):
            break

    # Method 2: Fallback
    if len(results) < max_results:
        fallback_pattern = re.compile(
            r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL
        )
        for match in fallback_pattern.finditer(resp.text):
            if _extract_from_match(match, seen_urls, results, max_results, is_fallback=True):
                break

    return results


@server.tool()
def duckduckgo_search(
    query: str,
    max_results: int = 5,
    timeout_s: float = 10.0,
    step_id: str | None = None,
) -> dict[str, Any]:
    """Perform a web search using DuckDuckGo.

    Args:
        query: The search query string
        max_results: Maximum number of results to return (default: 5, max: 20)
        timeout_s: Request timeout in seconds (default: 10.0)

    """
    if not query or not query.strip():
        logger.warning("Search request received with empty query")
        return {"error": "query is required"}

    logger.info(
        f"Executing search: query='{query.strip()}', max_results={max_results}, timeout={timeout_s}s",
    )

    try:
        max_results_i = int(max_results)
        if max_results_i <= 0:
            return {"error": "max_results must be > 0"}
        max_results_i = min(max_results_i, 20)

        timeout_f = float(timeout_s)
        if timeout_f <= 0:
            return {"error": "timeout_s must be > 0"}

        results = _search_ddg(query=query.strip(), max_results=max_results_i, timeout_s=timeout_f)
        if not results:
            logger.warning(f"Zero results found for query: '{query.strip()}'")
            return {
                "success": False,
                "error": "Zero results found. DDG might be blocking or layout changed.",
                "query": query.strip(),
            }
        logger.info(
            f"Search completed successfully for query: '{query.strip()}' - found {len(results)} results",
        )
        return {"success": True, "query": query.strip(), "results": results}
    except Exception as e:
        return {"error": str(e)}


def _scrape_opendatabot(company_name: str) -> dict[str, Any]:
    """Direct web scraping fallback for Opendatabot.ua."""
    try:
        # Try to detect if company_name is an EDRPOU code (8-10 digits)
        if re.match(r"^\d{8,10}$", company_name.strip()):
            search_url = f"https://opendatabot.ua/company/{company_name.strip()}"
        else:
            # Search by name
            search_url = f"https://opendatabot.ua/?q={company_name.strip()}"

        logger.info(f"Attempting direct Opendatabot scraping: {search_url}")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        response = requests.get(search_url, headers=headers, timeout=30)
        response.raise_for_status()

        if "Checking your browser" in response.text or "Cloudflare" in response.text:
            logger.warning("Opendatabot scraping blocked by CAPTCHA/Cloudflare")
            return {"error": "Opendatabot scraping blocked by anti-bot protection"}

        # Extract basic company information using regex patterns
        results = []

        # Look for company name
        name_pattern = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
        name_match = name_pattern.search(response.text)

        # Look for EDRPOU code
        edrpou_pattern = re.compile(r"ЄДРПОУ[^<]*?(\d{8,10})", re.IGNORECASE)
        edrpou_match = edrpou_pattern.search(response.text)

        # Look for address
        address_pattern = re.compile(r"Адреса[^<]*?<[^>]+>(.*?)</[^>]+>", re.IGNORECASE | re.DOTALL)
        address_match = address_pattern.search(response.text)

        if name_match or edrpou_match or address_match:
            result_item = {
                "title": name_match.group(1).strip() if name_match else "Company Information",
                "url": search_url,
                "snippet": "",
            }

            # Build snippet with found information
            snippet_parts = []
            if edrpou_match:
                snippet_parts.append(f"ЄДРПОУ: {edrpou_match.group(1)}")
            if address_match:
                address_text = re.sub(r"<.*?>", "", address_match.group(1)).strip()
                snippet_parts.append(f"Address: {address_text}")

            result_item["snippet"] = (
                ", ".join(snippet_parts) if snippet_parts else "Company data found"
            )
            results.append(result_item)
        else:
            # Try to find any company links on search results page
            company_links = re.findall(r'href="(/company/\d+)"', response.text)
            if company_links:
                for link in company_links[:3]:  # Top 3 results
                    results.append(
                        {
                            "title": f"Company Profile - {link.replace('/company/', '')}",
                            "url": f"https://opendatabot.ua{link}",
                            "snippet": "Company profile found on Opendatabot",
                        }
                    )

        if results:
            return {
                "success": True,
                "query": company_name.strip(),
                "results": results,
                "provider": "Opendatabot (Direct Web Scraping)",
                "fallback_used": True,
            }
        return {"error": "No company data found on Opendatabot"}

    except Exception as e:
        logger.error(f"Opendatabot scraping failed: {e}")
        return {"error": f"Opendatabot scraping error: {e!s}"}


def _scrape_youcontrol(company_name: str) -> dict[str, Any]:
    """Direct web scraping fallback for YouControl.com.ua."""
    try:
        # Try to detect if company_name is an EDRPOU code (8-10 digits)
        if re.match(r"^\d{8,10}$", company_name.strip()):
            search_url = (
                f"https://youcontrol.com.ua/catalog/company_details/{company_name.strip()}/"
            )
        else:
            # Search by name
            search_url = f"https://youcontrol.com.ua/catalog/search/?q={company_name.strip()}"

        logger.info(f"Attempting direct YouControl scraping: {search_url}")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        response = requests.get(search_url, headers=headers, timeout=30)
        response.raise_for_status()

        if "Checking your browser" in response.text or "Cloudflare" in response.text:
            logger.warning("YouControl scraping blocked by CAPTCHA/Cloudflare")
            return {"error": "YouControl scraping blocked by anti-bot protection"}

        # Extract basic company information using regex patterns
        results = []

        # Look for company name
        name_pattern = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
        name_match = name_pattern.search(response.text)

        # Look for EDRPOU code
        edrpou_pattern = re.compile(r"ЄДРПОУ[^<]*?(\d{8,10})", re.IGNORECASE)
        edrpou_match = edrpou_pattern.search(response.text)

        # Look for address
        address_pattern = re.compile(
            r"Юридична адреса[^<]*?<[^>]+>(.*?)</[^>]+>", re.IGNORECASE | re.DOTALL
        )
        address_match = address_pattern.search(response.text)

        if name_match or edrpou_match or address_match:
            result_item = {
                "title": name_match.group(1).strip() if name_match else "Company Information",
                "url": search_url,
                "snippet": "",
            }

            # Build snippet with found information
            snippet_parts = []
            if edrpou_match:
                snippet_parts.append(f"ЄДРПОУ: {edrpou_match.group(1)}")
            if address_match:
                address_text = re.sub(r"<.*?>", "", address_match.group(1)).strip()
                snippet_parts.append(f"Address: {address_text}")

            result_item["snippet"] = (
                ", ".join(snippet_parts) if snippet_parts else "Company data found"
            )
            results.append(result_item)
        else:
            # Try to find any company links on search results page
            company_links = re.findall(r'href="(/catalog/company_details/\d+/)', response.text)
            if company_links:
                for link in company_links[:3]:  # Top 3 results
                    results.append(
                        {
                            "title": f"Company Profile - {link.replace('/catalog/company_details/', '').strip('/')}",
                            "url": f"https://youcontrol.com.ua{link}",
                            "snippet": "Company profile found on YouControl",
                        }
                    )

        if results:
            return {
                "success": True,
                "query": company_name.strip(),
                "results": results,
                "provider": "YouControl (Direct Web Scraping)",
                "fallback_used": True,
            }
        return {"error": "No company data found on YouControl"}

    except Exception as e:
        logger.error(f"YouControl scraping failed: {e}")
        return {"error": f"YouControl scraping error: {e!s}"}


@server.tool()
def business_registry_search(company_name: str, step_id: str | None = None) -> dict[str, Any]:
    """Perform a specialized search for Ukrainian company data in business registries.
    Rules and targets are defined in search_protocol.txt.

    Enhanced with direct web scraping fallback for Opendatabot and YouControl.

    Args:
        company_name: The name or EDRPOU code of the company to search for.

    """
    if not company_name or not company_name.strip():
        logger.warning("Business registry search request received with empty company_name")
        return {"error": "company_name is required"}

    logger.info(f"Executing business registry search: company_name='{company_name.strip()}'")

    # Step 1: Try DuckDuckGo protocol search first
    result = _execute_protocol_search(
        "business",
        company_name,
        "DuckDuckGo (Optimized Registry Search)",
    )

    if result.get("success"):
        logger.info(
            f"Business registry search completed: found {len(result.get('results', []))} results",
        )
        return result
    logger.warning(f"DuckDuckGo search failed: {result.get('error', 'unknown error')}")

    # Step 2: Fallback to direct web scraping
    logger.info("Initiating fallback web scraping for business registry data")

    # Try Opendatabot first
    opendatabot_result = _scrape_opendatabot(company_name)
    if opendatabot_result.get("success"):
        logger.info(
            f"Opendatabot scraping successful: found {len(opendatabot_result.get('results', []))} results"
        )
        return opendatabot_result
    logger.warning(
        f"Opendatabot scraping failed: {opendatabot_result.get('error', 'unknown error')}"
    )

    # Try YouControl as second fallback
    youcontrol_result = _scrape_youcontrol(company_name)
    if youcontrol_result.get("success"):
        logger.info(
            f"YouControl scraping successful: found {len(youcontrol_result.get('results', []))} results"
        )
        return youcontrol_result
    logger.warning(f"YouControl scraping failed: {youcontrol_result.get('error', 'unknown error')}")

    # If all methods failed, return the original DuckDuckGo error with fallback context
    return {
        **result,
        "fallback_attempted": True,
        "fallback_errors": {
            "opendatabot": opendatabot_result.get("error", "unknown error"),
            "youcontrol": youcontrol_result.get("error", "unknown error"),
        },
    }


@server.tool()
def open_data_search(query: str, step_id: str | None = None) -> dict[str, Any]:
    """Search for datasets on the Ukrainian Open Data Portal (data.gov.ua).
    Rules and targets are defined in search_protocol.txt.

    Args:
        query: The search query for datasets.

    """
    if not query or not query.strip():
        logger.warning("Open data search request received with empty query")
        return {"error": "query is required"}

    logger.info(f"Executing open data search: query='{query.strip()}'")
    result = _execute_protocol_search("open_data", query, "DuckDuckGo (Open Data Portal Search)")
    if result.get("success"):
        logger.info(f"Open data search completed: found {len(result.get('results', []))} results")
    else:
        logger.warning(f"Open data search failed: {result.get('error', 'unknown error')}")
    return result


@server.tool()
def structured_data_search(query: str, step_id: str | None = None) -> dict[str, Any]:
    """Search for structured data sources (CSV, XLSX, JSON) on data.gov.ua.
    Uses refined queries targeting specific file types.

    Args:
        query: The search query for structured data.

    """
    if not query or not query.strip():
        logger.warning("Structured data search request received with empty query")
        return {"error": "query is required"}

    logger.info(f"Executing structured data search: query='{query.strip()}'")
    result = _execute_protocol_search(
        "structured_data", query, "DuckDuckGo (Structured Data Search)"
    )
    if result.get("success"):
        logger.info(
            f"Structured data search completed: found {len(result.get('results', []))} results"
        )
    else:
        logger.warning(f"Structured data search failed: {result.get('error', 'unknown error')}")
    return result


@server.tool()
def court_cases_search(query: str, step_id: str | None = None) -> dict[str, Any]:
    """Search for court cases and legal proceedings in Ukrainian registries.
    Rules and targets are defined in search_protocol.txt.

    Args:
        query: The name of the person or company, or a case number.

    """
    if not query or not query.strip():
        logger.warning("Court cases search request received with empty query")
        return {"error": "query is required"}

    logger.info(f"Executing court cases search: query='{query.strip()}'")
    result = _execute_protocol_search("court", query, "DuckDuckGo (Court Registry Search)")
    if result.get("success"):
        logger.info(f"Court cases search completed: found {len(result.get('results', []))} results")
    else:
        logger.warning(f"Court cases search failed: {result.get('error', 'unknown error')}")
    return result


if __name__ == "__main__":
    logger.info("Starting DuckDuckGo Search Server")
    logger.info(f"Loading search protocol from: {PROTOCOL_PATH}")
    server.run()
