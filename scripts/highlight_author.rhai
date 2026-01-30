import "scripts/config" as cfg;
let authors = params[0];

let authors_rg = RegexCaseInsensitive(`(?P<key>\b(${cfg::authors_rg})\b)`);
let authors = authors.map(|v|authors_rg.replace_all(v,"<span class=\"highlight-author\">$key</span>"));

let start = authors.shift();
authors.reduce(|sum, v| sum + ", " + v, start)