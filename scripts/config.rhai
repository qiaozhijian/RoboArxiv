let titles_type = ["Dataset", "Survey", "Review", "Overview"];
let titles_model = ["SLAM", "Odometry", "Registration", "Long-term", "Multi-session", "Planning", "Optimization", "Estimation", "Control", "Swarm", "Detection", "Segmentation", "Life", "estimator"];
let titles_method = ["Certifiable", "Self-Supervised", "Semi-Supervised", "Unsupervised", "Fusion", "Navigation", "Detect", "Decision", "Calibration", "Reinforcement", "Relocalization", "loop", "global", "outlier",
"localization", "dynamic", "sparsification", "graph", "clique"];
let titles =  titles_model + titles_method + titles_type;
let authors_array = ["Shaojie Shen", "Luca Carlone", "Yoshua Bengio", "Frank Dellaert", "Wolfram Burgard", "Davide Scaramuzza", "Marc Pollefeys", "Andrew Davison", "Daniel Cremers", "Heng Yang", "Fei Gao", 
"Tong Qin", "Wenchao Ding", "Fu Zhang", "Hesheng Wang", "Huan Yin", "Peng Yin", "Ming Liu", "Yue Wang", "Hang Zhao", "Xieyuanli Chen", "Boyu Zhou", "Timothy D. Barfoot", "Marc Pollefeys"];

let conferences = [
    // AI
    "AAAI", "AAMAS", "ACM MM", "AISTATS", "CORL", "RAM", "RAS", "TIM", "RAL", "TITS", "TMECH", "TASE", "IJRR", "ICRA", "ICTAI", "IJCAI", "IJCNN", "IROS", "KR", "KSEM", "SIGGRAPH", "STOC", "UAI", "PPSN", "PRICAI", "RSS", "JFR", "TRO",
    // CV
    "3DV", "ACCV", "ACM MM", "BMVC", "CVPR", "ECCV", "ICCV", "ICDAR", "ICIP", "ICME", "ICPR", "IEEE VIS", "MICCAI", "SIGGRAPH", "WACV",
    // DM
    "AKBC", "APWeb", "CIKM", "DASFAA", "ECML-PKDD", "ICDE", "ICDM", "ICDT", "KDD", "LREC", "MDM", "PAKDD", "PODS", "RecSys", "SDM", "SIGMOD", "VLDB", "WSDM", "WWW", "EDBT", "CIDR",
    // IR
    "ECIR", "ESWC", "ICMR", "ICTIR", "ISWC", "SIGIR",
    // ML
    "ACML", "AISTATS", "ECML", "ICLR", "ICML", "ML4H", "NeurIPS", "NIPS", "UAI",
    // NLP
    "AACL", "ACL", "CCL", "COLING", "COLT", "CoNLL", "EACL", "EMNLP", "ICASSP", "ICDAR", "ICONIP", "INTERSPEECH", "LREC", "NAACL", "NLPCC", "RepL4NLP", "SIGDIAL", "SemEval", "WANLP", "WASSA", "WOAH",
    // Arch
    "ASPLOS", "ATC", "DATE", "EuroSys", "FAST", "HPCA", "ISCA", "MICRO", "PPoPP", "SC", "SoCC",
    // System
    "FSE/ESEC", "ICSE", "ISSTA", "OSDI", "SOSP",
    // Security
    "ACSA", "AsiaCCS", "CCS", "DSN", "ESORICS", "EuroS&P", "ICICS", "NDSS", "RAID", "SP", "USENIX Security"
];

let start = conferences.shift();
let conferences_rg = conferences.reduce(|sum, v| sum + "|" + v, start);
let conferences_rg = "(" + conferences_rg + ")([\\s'-]*\\d+)?";

let start = titles.shift();
let title_rg = titles.reduce(|sum, v| sum + "|" + v, start);

let start = authors_array.shift();
let authors_rg = authors_array.reduce(|sum, v| sum + "|" + v, start);

export title_rg;
export authors_rg;
export conferences_rg;
