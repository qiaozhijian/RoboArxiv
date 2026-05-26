#!/usr/bin/env python3
"""
RoboArxiv - Modern self-contained daily arXiv digest builder.

Replaces the unmaintained NotCraft/ArxivFeed binary completely.
- Uses the official `arxiv` Python client (lukasschwab/arxiv.py)
- Strictly follows arXiv Terms of Use (proper UA, >=3s delay, retries)
- Produces the same logical data model as before (cache.json compatible)
- Renders a clean, modern, highly maintainable single-page site using Tailwind (CDN)

Usage:
    uv run scripts/build.py          # local preview (generates ./target/)
    # In GitHub Actions the same command works with `astral-sh/setup-uv`

Output:
    target/
        index.html
        cache.json
"""

# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "arxiv>=2.1.3",
#   "tomli>=2.0.1; python_version < '3.11'",
# ]
# ///

from __future__ import annotations

import html
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import arxiv

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]

# =============================================================================
# Configuration & Constants
# =============================================================================

UA = "RoboArxiv/1.0 (https://github.com/qiaozhijian/RoboArxiv; see repo issues for contact)"
ARXIV_DELAY = 3.5  # strictly > 3s per arXiv ToU
ARXIV_RETRIES = 6
ARXIV_PAGE_SIZE = 100

TARGET_DIR = Path("target")
CACHE_FILE = TARGET_DIR / "cache.json"
HTML_FILE = TARGET_DIR / "index.html"
PAPERS_PREVIEW_COUNT = 5


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)

# =============================================================================
# Data Model (exactly compatible with previous cache.json)
# =============================================================================

@dataclass
class Paper:
    id: str
    updated: str
    published: str
    title: str
    summary: str
    authors: list[str]
    pdf_url: str
    comment: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "id": self.id,
            "updated": self.updated,
            "published": self.published,
            "title": self.title,
            "summary": self.summary,
            "authors": self.authors,
            "pdf_url": self.pdf_url,
        }
        if self.comment:
            d["comment"] = self.comment
        return d


# date_iso -> category_title -> list[Paper]
Cache = dict[str, dict[str, list[Paper]]]


# =============================================================================
# Config Loading
# =============================================================================

@dataclass
class Source:
    category: str
    title: str
    limit: int = 300


@dataclass
class Config:
    site_title: str = "RoboArxiv"
    limit_days: int = 30
    cache_url: str | None = None
    sources: list[Source] = field(default_factory=list)


def load_config(path: Path = Path("config.toml")) -> Config:
    with path.open("rb") as f:
        raw = tomllib.load(f)

    cfg = Config(
        site_title=raw.get("site_title", "RoboArxiv"),
        limit_days=raw.get("limit_days", 30),
        cache_url=raw.get("cache_url"),
    )

    for s in raw.get("sources", []):
        cfg.sources.append(
            Source(
                category=s["category"],
                title=s["title"],
                limit=int(s.get("limit", 300)),
            )
        )
    return cfg


# =============================================================================
# arXiv Fetching (compliant & robust)
# =============================================================================

def make_client() -> arxiv.Client:
    """Create a properly configured arXiv client following official best practices."""
    client = arxiv.Client(
        page_size=ARXIV_PAGE_SIZE,
        delay_seconds=ARXIV_DELAY,
        num_retries=ARXIV_RETRIES,
    )
    client._session.headers.update({"User-Agent": UA})
    return client


def build_search_query(category: str) -> str:
    """Normalize config categories to valid arXiv API search queries."""
    query = category.strip()
    if any(token in query for token in ("(", " AND ", " OR ", "cat:", "+")):
        return query
    return f"cat:{query}"


def paper_from_dict(data: dict[str, Any]) -> Paper:
    return Paper(
        id=data["id"],
        updated=data["updated"],
        published=data["published"],
        title=data["title"],
        summary=data["summary"],
        authors=list(data["authors"]),
        pdf_url=data["pdf_url"],
        comment=data.get("comment"),
    )


def load_existing_cache(url: str | None, cutoff: datetime) -> Cache:
    if not url:
        return {}

    print(f"[cache] Loading existing cache from {url}")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
        print(f"[warn] Failed to load existing cache: {err}", file=sys.stderr)
        return {}

    cache: Cache = {}
    for day_key, categories in payload.items():
        day_dt = datetime.fromisoformat(day_key.replace("Z", "+00:00"))
        if day_dt < cutoff:
            continue

        cache[day_key] = {}
        for category, papers in categories.items():
            cache[day_key][category] = [paper_from_dict(p) for p in papers]

    print(f"[cache] Loaded {len(cache)} day buckets from remote cache")
    return cache


def merge_papers(cache: Cache, papers: list[Paper], category: str) -> None:
    for paper in papers:
        day_key = paper.updated.split("T")[0] + "T00:00:00Z"
        cache.setdefault(day_key, {})
        cache[day_key].setdefault(category, [])

        existing_ids = {item.id for item in cache[day_key][category]}
        if paper.id not in existing_ids:
            cache[day_key][category].append(paper)


def fetch_category(
    client: arxiv.Client,
    source: Source,
    cutoff: datetime,
) -> list[Paper]:
    """
    Fetch recent papers for one configured source.
    We query with 'cat:' or advanced query as written in config.
    Results are filtered client-side by the cutoff date.
    """
    print(f"[fetch] {source.title}  (cat: {source.category})  limit={source.limit}")

    # The original config used both simple "cat:cs.RO" and complex boolean queries.
    # The arxiv.py library accepts them directly as the `query` string.
    search = arxiv.Search(
        query=build_search_query(source.category),
        max_results=source.limit,
        sort_by=arxiv.SortCriterion.LastUpdatedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    papers: list[Paper] = []
    try:
        results = client.results(search)
        for r in results:
            # r.updated and r.published are datetime objects (timezone-aware)
            if r.updated < cutoff:
                continue

            # Build pdf url (use export subdomain for consistency, though arxiv.py already gives good one)
            pdf_url = r.pdf_url or f"https://arxiv.org/pdf/{r.get_short_id()}.pdf"
            if pdf_url.startswith("http://"):
                pdf_url = "https://" + pdf_url[7:]

            p = Paper(
                id=r.entry_id,
                updated=r.updated.isoformat(),
                published=r.published.isoformat(),
                title=r.title.strip().replace("\n", " "),
                summary=r.summary.strip().replace("\n", " "),
                authors=[a.name for a in r.authors],
                pdf_url=pdf_url,
                comment=r.comment,
            )
            papers.append(p)

            if len(papers) >= source.limit:
                break
    except Exception as e:
        print(f"[warn] fetch failed for {source.title}: {e}", file=sys.stderr)
        # We deliberately do not crash the whole build on one category failure.

    print(f"[fetch]   -> got {len(papers)} papers (after date filter)")
    return papers


def build_cache(cfg: Config) -> Cache:
    """Main fetching routine. Returns the nested structure used by the old system."""
    client = make_client()

    today = datetime.now(timezone.utc)
    cutoff = today - timedelta(days=max(cfg.limit_days, 1))

    # Truncate cutoff to day boundary (same spirit as original)
    cutoff = cutoff.replace(hour=0, minute=0, second=0, microsecond=0)

    raw = load_existing_cache(cfg.cache_url, cutoff)

    for source in cfg.sources:
        papers = fetch_category(client, source, cutoff)
        merge_papers(raw, papers, source.title)

    # Sort papers inside each bucket by updated desc (already mostly sorted)
    for day in raw.values():
        for cat_papers in day.values():
            cat_papers.sort(key=lambda x: x.updated, reverse=True)

    # Keep only the most recent N days that actually have data
    sorted_days = sorted(raw.keys(), reverse=True)[: cfg.limit_days]
    filtered = {d: raw[d] for d in sorted_days if raw[d]}

    print(f"[cache] Built cache with {len(filtered)} days")
    return filtered


# =============================================================================
# Rendering - Modern Beautiful Site (Tailwind via CDN)
# =============================================================================

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ site_title }}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;600&display=swap');
        
        :root {
            --primary: 234 179 8;
        }
        
        body {
            font-family: 'Inter', system_ui, sans-serif;
        }
        
        .font-display {
            font-family: 'Space Grotesk', 'Inter', sans-serif;
            font-weight: 600;
        }

        .paper-card {
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        .paper-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1);
        }

        .abstract {
            display: -webkit-box;
            -webkit-line-clamp: 4;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
        
        .abstract.expanded {
            -webkit-line-clamp: unset;
        }

        .section-header {
            font-size: 0.875rem;
            letter-spacing: 0.05em;
        }

        .arxiv-id {
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
            font-size: 0.75rem;
        }

        .category-pill {
            transition: all 0.1s ease;
        }

        .category-pill.active {
            background-color: rgb(234 179 8);
            color: black;
            border-color: rgb(234 179 8);
        }

        .stat {
            font-variant-numeric: tabular-nums;
        }

        .paper-title {
            font-size: 0.975rem;
            line-height: 1.35;
        }

        .meta {
            font-size: 0.75rem;
        }

        details > summary {
            list-style: none;
        }

        details > summary::-webkit-details-marker {
            display: none;
        }

        details > summary .chevron,
        details > summary .day-chevron {
            transition: transform 0.2s ease;
        }

        details[open] > summary .chevron,
        details[open] > summary .day-chevron {
            transform: rotate(180deg);
        }

        .day-section > summary,
        .category-section > summary {
            user-select: none;
        }

        .paper-item > summary:hover {
            background: rgba(39, 39, 42, 0.5);
        }
    </style>
</head>
<body class="bg-zinc-950 text-zinc-200">
    <!-- Header -->
    <header class="border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-lg sticky top-0 z-50">
        <div class="max-w-screen-2xl mx-auto px-6 py-5">
            <div class="flex items-center justify-between">
                <div class="flex items-center gap-x-4">
                    <div class="flex items-center gap-x-3">
                        <div class="w-9 h-9 bg-yellow-500 rounded-2xl flex items-center justify-center">
                            <i class="fa-solid fa-robot text-black text-3xl"></i>
                        </div>
                        <div>
                            <h1 class="font-display text-3xl tracking-tighter font-semibold">{{ site_title }}</h1>
                            <p class="text-[10px] text-zinc-500 -mt-1">Robotics • Embodied AI • World Models</p>
                        </div>
                    </div>
                </div>

                <div class="flex items-center gap-x-3 text-sm">
                    <div class="hidden md:flex items-center gap-x-2 px-3 py-1.5 rounded-2xl bg-zinc-900 border border-zinc-800">
                        <div class="w-2 h-2 bg-emerald-400 rounded-full animate-pulse"></div>
                        <span class="text-zinc-400">Updated daily</span>
                    </div>
                    
                    <a href="https://github.com/qiaozhijian/RoboArxiv" 
                       class="flex items-center gap-x-2 px-4 py-2 rounded-2xl border border-zinc-800 hover:bg-zinc-900 transition-colors"
                       target="_blank">
                        <i class="fa-brands fa-github"></i>
                        <span class="hidden sm:inline">GitHub</span>
                    </a>
                    
                    <button onclick="window.location.reload()"
                            class="px-4 py-2 rounded-2xl bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 flex items-center gap-x-2 text-sm transition-colors">
                        <i class="fa-solid fa-sync-alt"></i>
                        <span class="hidden sm:inline">Refresh</span>
                    </button>
                </div>
            </div>
        </div>
    </header>

    <!-- Controls -->
    <div class="max-w-screen-2xl mx-auto px-6 pt-8 pb-4">
        <div class="flex flex-col lg:flex-row lg:items-center gap-4">
            <!-- Search -->
            <div class="flex-1 max-w-xl">
                <div class="relative">
                    <i class="fa-solid fa-search absolute left-4 top-3.5 text-zinc-500"></i>
                    <input id="search-input"
                           type="text"
                           placeholder="搜索标题、作者、摘要..."
                           class="w-full bg-zinc-900 border border-zinc-800 focus:border-yellow-600 transition-colors rounded-3xl pl-11 pr-4 py-3 text-sm outline-none placeholder:text-zinc-500">
                </div>
            </div>

            <!-- Stats + Actions -->
            <div class="flex items-center gap-3 text-sm">
                <div class="px-4 py-2 bg-zinc-900 border border-zinc-800 rounded-3xl flex items-center gap-2">
                    <span class="text-zinc-400">最近</span>
                    <span id="total-papers" class="font-semibold stat text-yellow-400">{{ total_papers }}</span>
                    <span class="text-zinc-400">篇</span>
                </div>
                
                <button onclick="collapseToLatestDay()"
                        class="px-4 py-2 rounded-3xl border border-yellow-800/60 bg-yellow-900/20 hover:bg-yellow-900/40 text-yellow-400 transition-colors flex items-center gap-2 text-sm">
                    <i class="fa-solid fa-calendar-day"></i>
                    <span>仅最新一天</span>
                </button>

                <button onclick="expandAllSections()"
                        class="px-4 py-2 rounded-3xl border border-zinc-800 hover:bg-zinc-900 text-zinc-400 hover:text-zinc-200 transition-colors flex items-center gap-2 text-sm">
                    <i class="fa-solid fa-expand"></i>
                    <span>全部展开</span>
                </button>

                <button onclick="collapseAllSections()"
                        class="px-4 py-2 rounded-3xl border border-zinc-800 hover:bg-zinc-900 text-zinc-400 hover:text-zinc-200 transition-colors flex items-center gap-2 text-sm">
                    <i class="fa-solid fa-compress"></i>
                    <span>全部折叠</span>
                </button>

                <button onclick="clearFilters()"
                        class="px-4 py-2 rounded-3xl border border-zinc-800 hover:bg-zinc-900 text-zinc-400 hover:text-zinc-200 transition-colors flex items-center gap-2 text-sm">
                    <i class="fa-solid fa-times"></i>
                    <span>清空筛选</span>
                </button>
            </div>
        </div>

        <!-- Category Filters -->
        <div class="mt-4 flex flex-wrap gap-2" id="category-filters">
            {% for cat in categories %}
            <button data-category="{{ cat }}"
                    onclick="toggleCategoryFilter(this)"
                    class="category-pill px-4 py-1.5 text-sm rounded-2xl border border-zinc-700 bg-zinc-900 hover:border-zinc-500 active:bg-yellow-900/20 transition-all">
                {{ cat }}
            </button>
            {% endfor %}
        </div>
    </div>

    <!-- Main Content -->
    <main class="max-w-screen-2xl mx-auto px-6 pb-20">
        {% if not days %}
        <div class="text-center py-20 text-zinc-400">
            暂无数据。可能是今天 arXiv 尚未更新，或网络请求受限。
        </div>
        {% endif %}

        {% for day, subjects in days %}
        <section class="mb-10" data-day="{{ day }}">
            <!-- Date Header -->
            <div class="flex items-center gap-3 mb-4 px-1">
                <div class="font-display text-xl font-semibold tracking-tight">
                    {{ day.split('T')[0] }}
                </div>
                <div class="text-xs px-2.5 py-1 rounded-full bg-zinc-800 text-zinc-400 font-mono">
                    {{ subjects | sum(attribute='papers') | length }} 篇
                </div>
                <div class="flex-1 h-px bg-gradient-to-r from-zinc-800 to-transparent"></div>
            </div>

            {% for subject in subjects %}
            <div class="mb-6" data-category="{{ subject.name }}">
                <!-- Category Header -->
                <div class="flex items-center gap-2 mb-3 px-3">
                    <div class="font-semibold text-yellow-400 text-sm tracking-wider uppercase">
                        {{ subject.name }}
                    </div>
                    <div class="text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-400">
                        {{ subject.papers | length }}
                    </div>
                </div>

                <!-- Papers -->
                <div class="space-y-2">
                    {% for p in subject.papers %}
                    <div class="paper-card group bg-zinc-900 border border-zinc-800 hover:border-zinc-700 rounded-3xl px-5 py-4"
                         data-title="{{ p.title | lower }}"
                         data-authors="{{ p.authors | join(' ') | lower }}"
                         data-summary="{{ p.summary | lower }}">
                        
                        <div class="flex flex-col gap-2">
                            <!-- Title + Actions -->
                            <div class="flex items-start justify-between gap-3">
                                <a href="{{ p.id }}" target="_blank"
                                   class="paper-title font-medium text-zinc-100 group-hover:text-yellow-300 transition-colors leading-tight">
                                    {{ p.title }}
                                </a>
                                
                                <div class="flex items-center gap-1 shrink-0 opacity-70 group-hover:opacity-100 transition-opacity">
                                    <a href="{{ p.pdf_url }}" target="_blank"
                                       class="p-2 hover:bg-zinc-800 rounded-2xl text-yellow-400 hover:text-yellow-300"
                                       title="下载 PDF">
                                        <i class="fa-solid fa-file-pdf fa-lg"></i>
                                    </a>
                                    <button onclick="copyToClipboard('{{ p.id }}', this)"
                                            class="p-2 hover:bg-zinc-800 rounded-2xl text-zinc-400 hover:text-zinc-200"
                                            title="复制 arXiv 链接">
                                        <i class="fa-solid fa-link fa-lg"></i>
                                    </button>
                                </div>
                            </div>

                            <!-- Authors -->
                            <div class="text-sm text-zinc-400">
                                {{ p.authors | join(', ') }}
                            </div>

                            <!-- Meta -->
                            <div class="flex items-center gap-2 text-[11px] text-zinc-500 meta">
                                <span class="font-mono">arXiv:{{ p.id.split('/')[-1] }}</span>
                                {% if p.updated != p.published %}
                                <span class="px-1.5">•</span>
                                <span class="text-amber-400">updated</span>
                                {% endif %}
                                <span class="px-1.5">•</span>
                                <span>{{ p.published.split('T')[0] }}</span>
                            </div>

                            <!-- Abstract -->
                            <div class="mt-1">
                                <div class="abstract text-sm text-zinc-400 leading-relaxed cursor-pointer select-none"
                                     onclick="toggleAbstract(this)">
                                    {{ p.summary }}
                                </div>
                                <div class="mt-1 text-[10px] text-yellow-600/70 hover:text-yellow-500 cursor-pointer"
                                     onclick="toggleAbstract(this.previousElementSibling)">
                                    点击展开 / 收起摘要
                                </div>
                            </div>

                            {% if p.comment %}
                            <div class="text-xs text-zinc-500 bg-zinc-950 border border-zinc-800 rounded-2xl px-3 py-2">
                                <span class="text-zinc-400">Comment:</span> {{ p.comment }}
                            </div>
                            {% endif %}
                        </div>
                    </div>
                    {% endfor %}
                </div>
            </div>
            {% endfor %}
        </section>
        {% endfor %}
    </main>

    <!-- Footer -->
    <footer class="border-t border-zinc-800 py-8 text-center text-xs text-zinc-500">
        <div class="max-w-screen-2xl mx-auto px-6">
            Built with ❤️ using the official arXiv API • 
            <a href="https://github.com/qiaozhijian/RoboArxiv" class="hover:text-zinc-300">Source on GitHub</a>
            <span class="mx-2">•</span>
            Last generated: <span class="font-mono">{{ build_time }}</span>
        </div>
    </footer>

    <script>
        let activeCategories = new Set();

        function debounce(fn, delay) {
            let t;
            return (...args) => {
                clearTimeout(t);
                t = setTimeout(() => fn(...args), delay);
            };
        }

        function setDetailsOpen(selector, open) {
            document.querySelectorAll(selector).forEach(el => { el.open = open; });
        }

        function collapseToLatestDay() {
            document.querySelectorAll('.day-section').forEach((day, idx) => {
                day.open = idx === 0;
                day.querySelectorAll('.category-section').forEach(cat => { cat.open = false; });
                day.querySelectorAll('.extra-papers').forEach(extra => extra.classList.add('hidden'));
                day.querySelectorAll('.show-more-btn').forEach(btn => resetShowMoreBtn(btn));
            });
        }

        function expandAllSections() {
            setDetailsOpen('.day-section', true);
            setDetailsOpen('.category-section', true);
            document.querySelectorAll('.extra-papers').forEach(extra => extra.classList.remove('hidden'));
            document.querySelectorAll('.show-more-btn').forEach(btn => {
                btn.classList.add('hidden');
            });
        }

        function collapseAllSections() {
            setDetailsOpen('.day-section', false);
            setDetailsOpen('.category-section', false);
            document.querySelectorAll('.paper-item').forEach(p => { p.open = false; });
        }

        function resetShowMoreBtn(btn) {
            const hidden = btn.dataset.hidden;
            if (!hidden || hidden === '0') {
                btn.classList.add('hidden');
                return;
            }
            btn.classList.remove('hidden');
            btn.innerHTML = `显示其余 ${hidden} 篇 <i class="fa-solid fa-chevron-down ml-1"></i>`;
        }

        function toggleCategoryPapers(btn) {
            const wrapper = btn.previousElementSibling;
            if (!wrapper || !wrapper.classList.contains('extra-papers')) return;

            const isHidden = wrapper.classList.contains('hidden');
            if (isHidden) {
                wrapper.classList.remove('hidden');
                btn.innerHTML = `收起 <i class="fa-solid fa-chevron-up ml-1"></i>`;
            } else {
                wrapper.classList.add('hidden');
                const hidden = btn.dataset.hidden;
                btn.innerHTML = `显示其余 ${hidden} 篇 <i class="fa-solid fa-chevron-down ml-1"></i>`;
            }
        }

        function filterPapers() {
            const q = (document.getElementById('search-input').value || '').toLowerCase().trim();
            const hasSearch = q.length > 0;
            let visible = 0;

            document.querySelectorAll('.paper-item').forEach(item => {
                const title = item.dataset.title || '';
                const authors = item.dataset.authors || '';
                const summary = item.dataset.summary || '';
                const matchesSearch = !hasSearch || title.includes(q) || authors.includes(q) || summary.includes(q);

                const categorySection = item.closest('[data-category]');
                const cat = categorySection ? categorySection.dataset.category : '';
                const matchesCategory = activeCategories.size === 0 || activeCategories.has(cat);

                const show = matchesSearch && matchesCategory;
                item.style.display = show ? '' : 'none';
                if (show) visible++;

                if (show && hasSearch) {
                    item.closest('.day-section')?.setAttribute('open', '');
                    item.closest('.category-section')?.setAttribute('open', '');
                    const extra = item.closest('.extra-papers');
                    if (extra) extra.classList.remove('hidden');
                }
            });

            document.querySelectorAll('.category-section').forEach(section => {
                const visiblePapers = section.querySelectorAll('.paper-item:not([style*="display: none"])').length;
                section.style.display = visiblePapers > 0 ? '' : 'none';
            });

            document.querySelectorAll('.day-section').forEach(section => {
                const visibleCategories = section.querySelectorAll('.category-section:not([style*="display: none"])').length;
                section.style.display = visibleCategories > 0 ? '' : 'none';
            });

            const el = document.getElementById('total-papers');
            if (el) el.textContent = visible.toLocaleString();
        }

        const filterDebounced = debounce(filterPapers, 120);

        function toggleCategoryFilter(btn) {
            const cat = btn.dataset.category;
            if (activeCategories.has(cat)) {
                activeCategories.delete(cat);
                btn.classList.remove('active', 'border-yellow-500');
                btn.classList.add('border-zinc-700');
            } else {
                activeCategories.add(cat);
                btn.classList.add('active', 'border-yellow-500');
                btn.classList.remove('border-zinc-700');
            }
            filterPapers();
        }

        function clearFilters() {
            activeCategories.clear();
            document.querySelectorAll('#category-filters button').forEach(b => {
                b.classList.remove('active', 'border-yellow-500');
                b.classList.add('border-zinc-700');
            });
            document.getElementById('search-input').value = '';
            document.querySelectorAll('.paper-item').forEach(item => { item.style.display = ''; });
            document.querySelectorAll('.category-section, .day-section').forEach(el => { el.style.display = ''; });
            collapseToLatestDay();
            const total = document.querySelectorAll('.paper-item').length;
            const el = document.getElementById('total-papers');
            if (el) el.textContent = total.toLocaleString();
        }

        async function copyToClipboard(text, btn) {
            try {
                await navigator.clipboard.writeText(text);
                const original = btn.innerHTML;
                btn.innerHTML = '<i class="fa-solid fa-check text-emerald-400"></i> 已复制';
                setTimeout(() => { btn.innerHTML = original; }, 1200);
            } catch (e) {
                prompt('请手动复制：', text);
            }
        }

        function init() {
            const searchInput = document.getElementById('search-input');
            searchInput.addEventListener('input', filterDebounced);

            document.addEventListener('keydown', (e) => {
                if (e.key === '/' && document.activeElement.tagName === 'BODY') {
                    e.preventDefault();
                    searchInput.focus();
                }
                if (e.key === 'Escape') clearFilters();
            });

            collapseToLatestDay();
            console.log('%c[RoboArxiv] Collapsible UI initialized', 'color:#eab308');
        }

        window.addEventListener('DOMContentLoaded', init);
    </script>
</body>
</html>
"""

def render_html(cfg: Config, cache: Cache, build_time: str) -> str:
    """Render the modern site using a simple Jinja2-like substitution (no extra dep for prod)."""
    # We avoid adding jinja2 to keep the script ultra-light. Manual rendering is fine here.

    # Prepare data for template
    categories = [s.title for s in cfg.sources]

    # Convert cache to list of (day, list of {name, papers})
    days = []
    for day_iso in sorted(cache.keys(), reverse=True):
        subjects = []
        for cat_name, papers in cache[day_iso].items():
            subjects.append({
                "name": cat_name,
                "papers": [p.to_dict() for p in papers]
            })
        if subjects:
            days.append((day_iso, subjects))

    total_papers = sum(
        len(p) for day in cache.values() for p in day.values()
    )

    # Very small manual template engine (sufficient for our needs)
    html = HTML_TEMPLATE
    html = html.replace("{{ site_title }}", cfg.site_title)
    html = html.replace("{{ total_papers }}", str(total_papers))
    html = html.replace("{{ build_time }}", build_time)

    # Categories pills
    cat_html = "\n".join(
        f'<button data-category="{c}" onclick="toggleCategoryFilter(this)" '
        f'class="category-pill px-4 py-1.5 text-sm rounded-2xl border border-zinc-700 bg-zinc-900 hover:border-zinc-500 active:bg-yellow-900/20 transition-all">{c}</button>'
        for c in categories
    )
    html = html.replace("{% for cat in categories %}\n            <button data-category=\"{{ cat }}\"\n                    onclick=\"toggleCategoryFilter(this)\"\n                    class=\"category-pill px-4 py-1.5 text-sm rounded-2xl border border-zinc-700 bg-zinc-900 hover:border-zinc-500 active:bg-yellow-900/20 transition-all\">\n                {{ cat }}\n            </button>\n            {% endfor %}", cat_html)

    # Days and papers - this part is a bit heavy for pure replace, so we do it procedurally
    # For cleanliness, we will use a tiny helper to build the big sections.

    # Because the template is long, we will build the main content block in Python
    # and splice it in.

    main_content = build_main_content(days)
    html = html.replace(
        "{% if not days %}\n        <div class=\"text-center py-20 text-zinc-400\">\n            暂无数据。可能是今天 arXiv 尚未更新，或网络请求受限。\n        </div>\n        {% endif %}\n\n        {% for day, subjects in days %}\n        <section class=\"mb-10\" data-day=\"{{ day }}\">\n            <!-- Date Header -->\n            <div class=\"flex items-center gap-3 mb-4 px-1\">\n                <div class=\"font-display text-xl font-semibold tracking-tight\">\n                    {{ day.split('T')[0] }}\n                </div>\n                <div class=\"text-xs px-2.5 py-1 rounded-full bg-zinc-800 text-zinc-400 font-mono\">\n                    {{ subjects | sum(attribute='papers') | length }} 篇\n                </div>\n                <div class=\"flex-1 h-px bg-gradient-to-r from-zinc-800 to-transparent\"></div>\n            </div>\n\n            {% for subject in subjects %}\n            <div class=\"mb-6\" data-category=\"{{ subject.name }}\">\n                <!-- Category Header -->\n                <div class=\"flex items-center gap-2 mb-3 px-3\">\n                    <div class=\"font-semibold text-yellow-400 text-sm tracking-wider uppercase\">\n                        {{ subject.name }}\n                    </div>\n                    <div class=\"text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-400\">\n                        {{ subject.papers | length }}\n                    </div>\n                </div>\n\n                <!-- Papers -->\n                <div class=\"space-y-2\">\n                    {% for p in subject.papers %}\n                    <div class=\"paper-card group bg-zinc-900 border border-zinc-800 hover:border-zinc-700 rounded-3xl px-5 py-4\"\n                         data-title=\"{{ p.title | lower }}\"\n                         data-authors=\"{{ p.authors | join(' ') | lower }}\"\n                         data-summary=\"{{ p.summary | lower }}\">\n                        \n                        <div class=\"flex flex-col gap-2\">\n                            <!-- Title + Actions -->\n                            <div class=\"flex items-start justify-between gap-3\">\n                                <a href=\"{{ p.id }}\" target=\"_blank\"\n                                   class=\"paper-title font-medium text-zinc-100 group-hover:text-yellow-300 transition-colors leading-tight\">\n                                    {{ p.title }}\n                                </a>\n                                \n                                <div class=\"flex items-center gap-1 shrink-0 opacity-70 group-hover:opacity-100 transition-opacity\">\n                                    <a href=\"{{ p.pdf_url }}\" target=\"_blank\"\n                                       class=\"p-2 hover:bg-zinc-800 rounded-2xl text-yellow-400 hover:text-yellow-300\"\n                                       title=\"下载 PDF\">\n                                        <i class=\"fa-solid fa-file-pdf fa-lg\"></i>\n                                    </a>\n                                    <button onclick=\"copyToClipboard('{{ p.id }}', this)\"\n                                            class=\"p-2 hover:bg-zinc-800 rounded-2xl text-zinc-400 hover:text-zinc-200\"\n                                            title=\"复制 arXiv 链接\">\n                                        <i class=\"fa-solid fa-link fa-lg\"></i>\n                                    </button>\n                                </div>\n                            </div>\n\n                            <!-- Authors -->\n                            <div class=\"text-sm text-zinc-400\">\n                                {{ p.authors | join(', ') }}\n                            </div>\n\n                            <!-- Meta -->\n                            <div class=\"flex items-center gap-2 text-[11px] text-zinc-500 meta\">\n                                <span class=\"font-mono\">arXiv:{{ p.id.split('/')[-1] }}</span>\n                                {% if p.updated != p.published %}\n                                <span class=\"px-1.5\">•</span>\n                                <span class=\"text-amber-400\">updated</span>\n                                {% endif %}\n                                <span class=\"px-1.5\">•</span>\n                                <span>{{ p.published.split('T')[0] }}</span>\n                            </div>\n\n                            <!-- Abstract -->\n                            <div class=\"mt-1\">\n                                <div class=\"abstract text-sm text-zinc-400 leading-relaxed cursor-pointer select-none\"\n                                     onclick=\"toggleAbstract(this)\">\n                                    {{ p.summary }}\n                                </div>\n                                <div class=\"mt-1 text-[10px] text-yellow-600/70 hover:text-yellow-500 cursor-pointer\"\n                                     onclick=\"toggleAbstract(this.previousElementSibling)\">\n                                    点击展开 / 收起摘要\n                                </div>\n                            </div>\n\n                            {% if p.comment %}\n                            <div class=\"text-xs text-zinc-500 bg-zinc-950 border border-zinc-800 rounded-2xl px-3 py-2\">\n                                <span class=\"text-zinc-400\">Comment:</span> {{ p.comment }}\n                            </div>\n                            {% endif %}\n                        </div>\n                    </div>\n                    {% endfor %}\n                </div>\n            </div>\n            {% endfor %}\n        </section>\n        {% endfor %}",
        main_content
    )

    return html


def render_paper_card(paper: dict[str, Any]) -> str:
    authors = ", ".join(paper["authors"])
    updated_badge = ""
    if paper["updated"] != paper["published"]:
        updated_badge = '<span class="px-1.5">•</span><span class="text-amber-400">updated</span>'

    comment_html = ""
    if paper.get("comment"):
        comment_html = (
            f'<div class="text-xs text-zinc-500 bg-zinc-950 border border-zinc-800 rounded-2xl px-3 py-2">'
            f'<span class="text-zinc-400">Comment:</span> {esc(paper["comment"])}</div>'
        )

    arxiv_short = paper["id"].split("/")[-1]
    paper_id = esc(paper["id"])

    return f"""
    <details class="paper-item bg-zinc-900/80 border border-zinc-800 hover:border-zinc-700 rounded-2xl overflow-hidden"
             data-title="{esc(paper['title'].lower())}"
             data-authors="{esc(authors.lower())}"
             data-summary="{esc(paper['summary'].lower())}">
        <summary class="cursor-pointer px-4 py-3 select-none">
            <div class="flex items-start justify-between gap-3">
                <div class="min-w-0 flex-1">
                    <div class="paper-title font-medium text-zinc-100 leading-tight">{esc(paper['title'])}</div>
                    <div class="text-xs text-zinc-500 mt-1 truncate">{esc(authors)}</div>
                </div>
                <div class="flex items-center gap-2 shrink-0 text-zinc-500 pt-0.5">
                    <span class="font-mono text-[10px] hidden sm:inline">{esc(arxiv_short)}</span>
                    <i class="fa-solid fa-chevron-down chevron text-[10px]"></i>
                </div>
            </div>
        </summary>
        <div class="px-4 pb-4 border-t border-zinc-800/80 pt-3 space-y-3">
            <div class="flex items-center gap-2 text-[11px] text-zinc-500 meta">
                <span class="font-mono">arXiv:{esc(arxiv_short)}</span>
                {updated_badge}
                <span class="px-1.5">•</span>
                <span>{esc(paper['published'].split('T')[0])}</span>
            </div>
            <div class="text-sm text-zinc-400 leading-relaxed">{esc(paper['summary'])}</div>
            {comment_html}
            <div class="flex flex-wrap items-center gap-2 pt-1">
                <a href="{paper_id}" target="_blank"
                   class="px-3 py-1.5 text-xs rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-300">
                    <i class="fa-solid fa-up-right-from-square mr-1"></i> arXiv
                </a>
                <a href="{esc(paper['pdf_url'])}" target="_blank"
                   class="px-3 py-1.5 text-xs rounded-xl bg-yellow-900/30 hover:bg-yellow-900/50 text-yellow-400">
                    <i class="fa-solid fa-file-pdf mr-1"></i> PDF
                </a>
                <button type="button" onclick="copyToClipboard('{paper_id}', this)"
                        class="px-3 py-1.5 text-xs rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-400">
                    <i class="fa-solid fa-link mr-1"></i> 复制
                </button>
            </div>
        </div>
    </details>
    """


def build_main_content(days: list) -> str:
    """Build collapsible day/category sections with paper preview limits."""
    if not days:
        return '<div class="text-center py-20 text-zinc-400">暂无数据。可能是今天 arXiv 尚未更新，或网络请求受限。</div>'

    parts: list[str] = []
    for day_idx, (day_iso, subjects) in enumerate(days):
        day_str = day_iso.split("T")[0]
        total_in_day = sum(len(s["papers"]) for s in subjects)
        day_open = " open" if day_idx == 0 else ""

        parts.append(f"""
        <details class="day-section mb-4 border border-zinc-800 rounded-3xl overflow-hidden bg-zinc-950/50"{day_open} data-day="{esc(day_iso)}">
            <summary class="cursor-pointer px-5 py-4 bg-zinc-900 hover:bg-zinc-800/80 transition-colors flex items-center gap-3">
                <i class="fa-solid fa-chevron-down day-chevron text-yellow-500 text-sm"></i>
                <div class="font-display text-xl font-semibold tracking-tight">{esc(day_str)}</div>
                <div class="text-xs px-2.5 py-1 rounded-full bg-zinc-800 text-zinc-400 font-mono">{total_in_day} 篇</div>
                <div class="flex-1"></div>
                <span class="text-xs text-zinc-500 hidden sm:inline">点击展开/折叠</span>
            </summary>
            <div class="px-4 pb-4 pt-2 space-y-3">
        """)

        for subj in subjects:
            papers = subj["papers"]
            preview = papers[:PAPERS_PREVIEW_COUNT]
            extra = papers[PAPERS_PREVIEW_COUNT:]
            extra_count = len(extra)

            parts.append(f"""
            <details class="category-section border border-zinc-800/70 rounded-2xl overflow-hidden bg-zinc-900/30"
                     data-category="{esc(subj['name'])}">
                <summary class="cursor-pointer px-4 py-3 hover:bg-zinc-800/40 transition-colors flex items-center gap-2">
                    <i class="fa-solid fa-chevron-down chevron text-yellow-500/80 text-xs"></i>
                    <div class="font-semibold text-yellow-400 text-sm tracking-wider uppercase">{esc(subj['name'])}</div>
                    <div class="text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-400">{len(papers)}</div>
                    <span class="text-[10px] text-zinc-600 ml-auto">默认显示 {min(len(papers), PAPERS_PREVIEW_COUNT)} 篇</span>
                </summary>
                <div class="px-3 pb-3 space-y-2">
            """)

            for paper in preview:
                parts.append(render_paper_card(paper))

            if extra:
                parts.append('<div class="extra-papers hidden space-y-2">')
                for paper in extra:
                    parts.append(render_paper_card(paper))
                parts.append("</div>")
                parts.append(f"""
                <button type="button" onclick="toggleCategoryPapers(this)"
                        class="show-more-btn w-full mt-2 py-2.5 text-sm text-yellow-500 hover:text-yellow-400 hover:bg-yellow-900/10 border border-dashed border-zinc-700 rounded-2xl transition-colors"
                        data-hidden="{extra_count}">
                    显示其余 {extra_count} 篇 <i class="fa-solid fa-chevron-down ml-1"></i>
                </button>
                """)

            parts.append("</div></details>")

        parts.append("</div></details>")

    return "".join(parts)


def write_outputs(cache: Cache, html: str) -> None:
    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    with CACHE_FILE.open("w", encoding="utf-8") as f:
        # Convert Paper objects to plain dicts
        serializable = {
            day: {cat: [p.to_dict() for p in plist] for cat, plist in cats.items()}
            for day, cats in cache.items()
        }
        json.dump(serializable, f, ensure_ascii=False, indent=2)

    with HTML_FILE.open("w", encoding="utf-8") as f:
        f.write(html)

    print(f"[output] Wrote {CACHE_FILE} and {HTML_FILE}")


# =============================================================================
# Main
# =============================================================================

def main():
    print("=== RoboArxiv Modern Builder ===")
    cfg = load_config()
    print(f"Config loaded: {len(cfg.sources)} sources, limit_days={cfg.limit_days}")

    cache = build_cache(cfg)

    build_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    html = render_html(cfg, cache, build_time)

    write_outputs(cache, html)

    print("=== Build finished successfully ===")
    print(f"Open file://{HTML_FILE.resolve()} to preview locally.")


if __name__ == "__main__":
    main()
