import "scripts/config" as cfg;
let comment = params[0];

let conferences_rg = RegexCaseInsensitive(`(?P<key>\b(${cfg::conferences_rg})\b)`);

if comment != () {
    let conference = conferences_rg.find(comment);
    let conference = conference.text;

    let conference = if conference != "" {
        "<span class=\"chip\">" + conference + "</span>"
    } else {
        ""
    };

    conference
} else {
    ""
}

