import "scripts/config" as cfg;

let title = params[0];
let authors = params[1];
let comment = params[2];

title.trim();

let title_rg = RegexCaseInsensitive(`(?P<key>\b(${cfg::title_rg})\b)`);
let authors_rg = RegexCaseInsensitive(`(?P<key>\b(${cfg::authors_rg})\b)`);
let labs_rg = RegexCaseInsensitive(`(?P<key>(${cfg::labs_rg}))`);

let title = title_rg.replace_all(title,"<span class=\"highlight-title\">$key</span>");

let has_top_author = true in authors.map(|v|authors_rg.is_match(v));
let has_top_lab = if comment != () { labs_rg.is_match(comment) } else { false };

let star = if has_top_author && has_top_lab {
    "★★"
} else if has_top_author || has_top_lab {
    "★"
} else {
    "☆"
};

let title = "<span class=\"highlight-title\">" + star + "</span> " + title;

title
