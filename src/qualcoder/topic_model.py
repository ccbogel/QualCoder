# -*- coding: utf-8 -*-

"""
This file is part of QualCoder.

QualCoder is free software: you can redistribute it and/or modify it under the
terms of the GNU Lesser General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later version.

QualCoder is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with QualCoder.
If not, see <https://www.gnu.org/licenses/>.

Authors: Colin Curtain C, Kai Droege, Justin Missaghieh--Poncet, Lorenzo Salomao
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
https://qualcoder.org/
"""

"""BERT-based topic modeling of the corpus (BERTopic-style), pure Python.

Pipeline (Grootendorst 2022, "BERTopic: Neural Topic Modeling with a Class-based
TF-IDF procedure", https://arxiv.org/abs/2203.05794), implemented with the
dependencies already used by QualCoder's AI features:
- embeddings: sentence-transformers (BERT-based), imported lazily so the rest of
  the module works and is testable without it;
- clustering: scikit-learn KMeans on L2-normalized embeddings (HDBSCAN if the
  optional package is installed), with a numpy fallback;
- topic words: class-based TF-IDF (c-TF-IDF).

If the optional `bertopic` package is installed, the same corpus can be run
through it for comparison (see the PR description); this module is the
dependency-light default.
"""

import logging

import numpy as np

from .irastats.text import load_stopwords, tokenize

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
AI_MODEL = "intfloat/multilingual-e5-large"  # downloaded by QualCoder's AI setup


def compute_embeddings(texts: list, model_name: str = DEFAULT_MODEL) -> np.ndarray:
    """BERT-based sentence embeddings with sentence-transformers (lazy import).

    Raises ImportError with a clear message when sentence-transformers is not
    available (e.g. AI features not set up).
    """

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as err:
        raise ImportError(
            "sentence-transformers is required for BERT embeddings "
            "(it is installed with QualCoder's AI features)."
        ) from err
    model = SentenceTransformer(model_name)
    return np.asarray(model.encode(list(texts), show_progress_bar=False), dtype=float)


def _kmeans_numpy(X: np.ndarray, k: int, seed: int = 42, max_iter: int = 100) -> np.ndarray:
    """Small Lloyd's k-means fallback (numpy only), deterministic with `seed`. """

    rng = np.random.default_rng(seed)
    n = X.shape[0]
    k = max(1, min(k, n))
    centers = X[rng.choice(n, size=k, replace=False)].copy()
    labels = np.full(n, -1, dtype=int)
    for _ in range(max_iter):
        dists = ((X[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        new_labels = dists.argmin(axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for c in range(k):
            if (labels == c).any():
                centers[c] = X[labels == c].mean(axis=0)
    return labels


def cluster_embeddings(embeddings, n_clusters: int = None, min_cluster_size: int = 5,
                       seed: int = 42) -> np.ndarray:
    """Cluster the embeddings. Returns an int label per document (-1 = noise when
    HDBSCAN is used). Uses HDBSCAN when the optional package is installed, else
    scikit-learn KMeans, else a numpy k-means fallback.

    Args:
        embeddings: (n_docs, dim) array-like
        n_clusters: number of topics; if None, estimated from min_cluster_size
            (heuristic: n_docs / min_cluster_size, capped at 20, at least 2)
        min_cluster_size: minimum documents per topic (HDBSCAN) / used for the
            n_clusters heuristic
        seed: random seed (deterministic results)
    """

    X = np.asarray(embeddings, dtype=float)
    n = X.shape[0]
    if n == 0:
        return np.zeros(0, dtype=int)
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    X = X / norms
    if n_clusters is None:
        n_clusters = max(2, min(n // max(min_cluster_size, 1), 20))
    n_clusters = max(1, min(n_clusters, n))
    try:
        import hdbscan  # optional
        clusterer = hdbscan.HDBSCAN(min_cluster_size=max(min_cluster_size, 2))
        labels = clusterer.fit_predict(X)
        if len(set(labels)) >= 2:
            return labels
    except ImportError:
        pass
    try:
        from sklearn.cluster import KMeans
        return KMeans(n_clusters=n_clusters, random_state=seed, n_init=10).fit_predict(X)
    except ImportError:
        return _kmeans_numpy(X, n_clusters, seed=seed)


def ctfidf_topics(texts: list, labels, top_n: int = 10, stopwords: set = None,
                 language: str = "fr") -> dict:
    """Class-based TF-IDF (c-TF-IDF, as in BERTopic) per topic.

    For each topic c: score(w, c) = (count(w, c) / total_words(c)) * log(1 + n_topics / df(w))
    where df(w) is the number of topics containing w.
    Returns:
        {label: [(word, score), ...] sorted by decreasing score}, label -1 is noise.
    """

    labels = np.asarray(labels)
    stopwords = stopwords or set()
    tokenized = [tokenize(text, lowercase=True) for text in texts]
    tokenized = [[t for t in tokens if t not in stopwords] for tokens in tokenized]
    unique_labels = sorted(set(labels.tolist()))
    topic_labels = [l for l in unique_labels if l != -1]
    n_topics = max(len(topic_labels), 1)
    # per-topic word sets and counts
    label_words = {}
    label_counts = {}
    label_totals = {}
    for label in unique_labels:
        docs = [tokenized[i] for i in range(len(texts)) if labels[i] == label]
        counts = {}
        for d in docs:
            for w in d:
                counts[w] = counts.get(w, 0) + 1
        label_counts[label] = counts
        label_words[label] = set(counts)
        label_totals[label] = sum(len(d) for d in docs) or 1
    # df(w) = number of non-noise topics containing w
    df = {}
    for label in topic_labels:
        for w in label_words[label]:
            df[w] = df.get(w, 0) + 1
    result = {}
    for label in unique_labels:
        counts = label_counts[label]
        total = label_totals[label]
        scores = {w: (c / total) * np.log(1 + n_topics / df.get(w, 1)) for w, c in counts.items()}
        result[label] = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]
    return result


def topics_summary(texts: list, labels, top_n: int = 10, stopwords: set = None,
                   language: str = "fr") -> list:
    """Topic summary: for each topic (label != -1), its size, top c-TF-IDF words and
    the most representative documents (closest to the topic centroid in the raw
    texts is not available here, so the longest documents of the topic are used).
    Returns a list of dicts sorted by decreasing size:
    {topic, size, top_words: [(word, score)], representative_texts: [str]}
    """

    labels = np.asarray(labels)
    ctfidf = ctfidf_topics(texts, labels, top_n=top_n, stopwords=stopwords, language=language)
    topics = []
    for label in sorted(set(labels.tolist())):
        if label == -1:
            continue
        idx = [i for i in range(len(texts)) if labels[i] == label]
        reps = sorted(idx, key=lambda i: -len(texts[i]))[:3]
        topics.append({
            "topic": int(label),
            "size": len(idx),
            "top_words": ctfidf.get(label, []),
            "representative_texts": [texts[i] for i in reps],
        })
    topics.sort(key=lambda t: (-t["size"], t["topic"]))
    return topics


def bertopic_analysis(segments: list, model_name: str = DEFAULT_MODEL, n_clusters: int = None,
                      min_cluster_size: int = 5, top_n: int = 10, language: str = "fr",
                      stem: bool = False, custom_stopwords_path: str = None, seed: int = 42) -> dict:
    """Full BERTopic-style analysis of the corpus segments.

    Args:
        segments: list of segment dicts (irastats.corpus.build_segments)
        model_name: sentence-transformers model for the BERT embeddings
        n_clusters: number of topics (None = heuristic from min_cluster_size)
        min_cluster_size: minimum documents per topic
        top_n: number of top words per topic
        language: for the stopwords used in the c-TF-IDF
        stem: apply light stemming before the c-TF-IDF
        custom_stopwords_path: optional editable stopwords file
        seed: random seed (deterministic clustering)
    Returns:
        dict with model, n_docs, n_topics, noise count, topics (topics_summary),
        labels (per segment).
    """

    texts = [segment["text"] for segment in segments]
    if not texts:
        raise ValueError("No segments to analyze")
    embeddings = compute_embeddings(texts, model_name=model_name)
    labels = cluster_embeddings(embeddings, n_clusters=n_clusters,
                                min_cluster_size=min_cluster_size, seed=seed)
    stopwords = load_stopwords(language, custom_path=custom_stopwords_path)
    if stem:
        from .irastats.text import light_stem, normalize_tokens
        texts = [" ".join(normalize_tokens(tokenize(t), stopwords=stopwords, stem=True, language=language))
                 for t in texts]
        stopwords = set()
    topics = topics_summary(texts, labels, top_n=top_n, stopwords=stopwords, language=language)
    n_noise = int((np.asarray(labels) == -1).sum())
    return {
        "model": model_name,
        "n_docs": len(texts),
        "n_topics": len(topics),
        "n_noise": n_noise,
        "topics": topics,
        "labels": [int(l) for l in labels],
    }


def plot_topic_sizes(result: dict, figsize=(9, 5)):
    """Bar chart of the topic sizes (matplotlib Figure, no backend needed). """

    from matplotlib.figure import Figure

    fig = Figure(figsize=figsize)
    ax = fig.add_subplot(111)
    topics = result["topics"]
    if not topics:
        ax.set_title("BERTopic: no topics")
        return fig
    names = [f"topic {t['topic']}" for t in topics]
    sizes = [t["size"] for t in topics]
    ax.bar(names, sizes, color="#22a7f0", edgecolor="#115f9a")
    ax.set_ylabel(_("Documents"))
    ax.set_title(_("BERTopic: topic sizes") + f" ({result['n_topics']} " + _("topics") + ")")
    for i, s in enumerate(sizes):
        ax.annotate(str(s), (i, s), ha="center", va="bottom", fontsize=8)
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    return fig


TOPIC_PALETTE = ["#e14b31", "#22a7f0", "#26CC00", "#ab3da9", "#FFA600", "#009C1A",
                 "#0091ea", "#c2185b", "#5d4037", "#00897b"]


def topic_by_variable(labels, segment_variables: list, variable: str):
    """Distribution of the topics across the modalities of a partition variable
    (code, case, document, file/case attribute) - the "topics x variable" cross.

    Args:
        labels: topic label per segment (from bertopic_analysis)
        segment_variables: variables dict of each segment
        variable: variable key ("code", "case", "document", "file:<name>", ...)
    Returns:
        (modalities, topic_ids, counts) with counts[i, j] = number of segments
        with modality i and topic j; noise (label -1) and empty modalities are
        excluded.
    """

    labels = np.asarray(labels)
    values = [str(v.get(variable, "")) for v in segment_variables]
    modalities = sorted({v for v in values if v != ""})
    topic_ids = sorted({int(l) for l in labels.tolist() if int(l) != -1})
    counts = np.zeros((len(modalities), len(topic_ids)), dtype=int)
    modality_index = {m: i for i, m in enumerate(modalities)}
    topic_index = {t: j for j, t in enumerate(topic_ids)}
    for value, label in zip(values, labels.tolist()):
        if value == "" or int(label) == -1:
            continue
        counts[modality_index[value], topic_index[int(label)]] += 1
    return modalities, topic_ids, counts


def plot_topic_distribution(modalities, topic_ids, counts, figsize=(10, 6)):
    """Stacked bar chart of the topic distribution per modality of a variable
    (matplotlib Figure, no backend needed). """

    from matplotlib.figure import Figure

    fig = Figure(figsize=figsize)
    ax = fig.add_subplot(111)
    if not modalities:
        ax.set_title(_("Topic distribution: no variable"))
        return fig
    bottoms = np.zeros(len(modalities))
    for j, topic in enumerate(topic_ids):
        ax.bar(modalities, counts[:, j], bottom=bottoms, label=f"topic {topic}",
               color=TOPIC_PALETTE[j % len(TOPIC_PALETTE)], edgecolor="white", linewidth=0.4)
        bottoms += counts[:, j]
    ax.set_ylabel(_("Documents"))
    ax.set_title(_("Topic distribution by variable"))
    ax.legend(fontsize=7)
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    return fig
