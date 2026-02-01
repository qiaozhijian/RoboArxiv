/* Exapand/Collapse with TAB key */
var expanded = false;
document.onkeydown = function (e) {
    if (e.keyCode === 9) {
        expanded = !expanded;
        document.querySelectorAll("details").forEach(detail => detail.open = expanded);
        return false;
    }
};

/* Switch Theme */
const toggleSwitch = document.querySelector('.theme-switch input[type="checkbox"]');

/* In-page Search */
const searchInput = document.getElementById('search-input');
const featuredToggle = document.getElementById('featured-toggle');
let isFeaturedOnly = false;

function filterArticles() {
    const query = searchInput ? searchInput.value.toLowerCase() : "";
    const articles = document.querySelectorAll('.day-container article article');
    
    articles.forEach(article => {
        const titleText = article.querySelector('.article-expander-title').textContent;
        const authors = article.querySelector('.article-authors').textContent.toLowerCase();
        const summary = article.querySelector('.article-summary-box-inner').textContent.toLowerCase();
        
        const hasStar = titleText.includes('★');
        const hasConference = article.querySelector('.chip') !== null;
        const matchesSearch = titleText.toLowerCase().includes(query) || authors.includes(query) || summary.includes(query);
        
        let shouldShow = matchesSearch;
        if (isFeaturedOnly) {
            shouldShow = shouldShow && (hasStar || hasConference);
        }
        
        article.style.display = shouldShow ? '' : 'none';
    });

    // Hide empty sections
    document.querySelectorAll('.day-container').forEach(day => {
        let hasVisible = false;
        day.querySelectorAll('article article').forEach(a => {
            if (a.style.display !== 'none') hasVisible = true;
        });
        day.style.display = hasVisible ? '' : 'none';
    });
}

if (searchInput) {
    searchInput.addEventListener('input', filterArticles);
}

if (featuredToggle) {
    featuredToggle.addEventListener('click', function() {
        isFeaturedOnly = !isFeaturedOnly;
        featuredToggle.classList.toggle('active');
        filterArticles();
    });
}

/* Featured Legend Logic */
const infoIcon = document.getElementById('featured-info-icon');
const legend = document.getElementById('featured-legend');
const legendClose = document.querySelector('.legend-close');

if (infoIcon && legend) {
    infoIcon.addEventListener('click', function() {
        legend.classList.toggle('hidden');
    });
}

if (legendClose && legend) {
    legendClose.addEventListener('click', function() {
        legend.classList.add('hidden');
    });
}

/* Auto Detect Code Links */
document.querySelectorAll('.article-summary-box-inner span').forEach(span => {
    const text = span.textContent;
    const githubMatch = text.match(/https?:\/\/github\.com\/[^\s)\]]+/);
    if (githubMatch) {
        const codeUrl = githubMatch[0];
        const authorsDiv = span.closest('article').querySelector('.article-authors');
        if (authorsDiv && !authorsDiv.querySelector('.code-link')) {
            const codeLink = document.createElement('a');
            codeLink.href = codeUrl;
            codeLink.className = 'code-link';
            codeLink.innerHTML = '<i class="ri-code-s-slash-line" title="Source Code"></i>';
            codeLink.style.marginLeft = '10px';
            codeLink.style.color = 'var(--nord0E)';
            authorsDiv.insertBefore(codeLink, authorsDiv.firstChild);
        }
    }
});

function switchTheme(e) {
    if (e.target.checked) {
        document.documentElement.setAttribute('data-theme', 'light');
        document.getElementById("theme-icon").className = "ri-sun-line";
        localStorage.setItem('theme', 'light'); //add this
    } else {
        document.documentElement.setAttribute('data-theme', 'dark');
        document.getElementById("theme-icon").className = "ri-moon-line";
        localStorage.setItem('theme', 'dark'); //add this
    }
}

toggleSwitch.addEventListener('change', switchTheme, false);
const currentTheme = localStorage.getItem('theme') ? localStorage.getItem('theme') : null;
if (currentTheme) {
    document.documentElement.setAttribute('data-theme', currentTheme);
    if (currentTheme === 'light') {
        toggleSwitch.checked = true;
    }
}

const timestamp = document.getElementById("build-timestamp");
const timestamp_local = new Date(timestamp.getAttribute("datetime")).toLocaleString();

const badge = document.getElementById("build-timestamp-badge");
// badge.src = `https://img.shields.io/github/workflow/status/mlnlp-world/myarxiv/Update?=${timestamp_local}&style=for-the-badge`
