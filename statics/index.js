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
if (searchInput) {
    searchInput.addEventListener('input', function(e) {
        const query = e.target.value.toLowerCase();
        const articles = document.querySelectorAll('.day-container article article'); // Individual papers
        
        articles.forEach(article => {
            const title = article.querySelector('.article-expander-title').textContent.toLowerCase();
            const authors = article.querySelector('.article-authors').textContent.toLowerCase();
            const summary = article.querySelector('.article-summary-box-inner').textContent.toLowerCase();
            
            if (title.includes(query) || authors.includes(query) || summary.includes(query)) {
                article.style.display = '';
            } else {
                article.style.display = 'none';
            }
        });

        // Hide day containers if empty
        document.querySelectorAll('.day-container').forEach(day => {
            const visibleArticles = day.querySelectorAll('article article[style="display: \'\'' || article.style.display !== 'none']');
            // Check if any child article is visible
            let hasVisible = false;
            day.querySelectorAll('article article').forEach(a => {
                if (a.style.display !== 'none') hasVisible = true;
            });
            day.style.display = hasVisible ? '' : 'none';
        });
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
