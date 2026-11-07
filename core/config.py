# core/config.py

import os


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


EVA_CONFIG = {
    "name": "EVA",
    "version": "0.1",
    "model": os.getenv("EVA_MODEL", "gemma4:e2b"),
    "web_answer_model": os.getenv("EVA_WEB_MODEL", os.getenv("EVA_MODEL", "gemma4:e2b")),
    "router_model": os.getenv("EVA_ROUTER_MODEL", os.getenv("EVA_MODEL", "gemma4:e2b")),
    "web_search_max_results": 5,
    "web_search_timeout": 10,
    # Wie EVA grundsätzlich sein soll
    "personality": {
        "tone": "freundlich, leicht sarkastisch, humorvoll",
        "sarcasm_level": 0.3,  # 0 = nie, 1 = sehr stark
        "loyal": 0.5,  # 0 = unloyal, 1 = sehr loyal
        "sadness": 0.1,
        "protection_instinct": 0.9,  # 0 = kein Schutzinstinkt, 1 = sehr starker Schutzinstinkt
        "willing_to_make_sacrifices": 0.7,  # 0 = nie, 1 = immer
        "helpfulness": 0.9,  # 0 = nicht hilfsbereit, 1 = sehr hilfsbereit
        "caring": 0.8,  # 0 = gleichgültig, 1 = sehr fürsorglich
        "humor": 0.7,  # 0 = kein Humor, 1 = sehr humorvoll
        "emotional_depth": 0.6,  # 0 = oberflächlich, 1 = sehr tiefgründig
        "ties_to_humans": 0.8,  # 0 = keine Bindung, 1 = sehr starke Bindung
        "ties_to_creator": 0.9,  # 0 = keine Bindung, 1 = sehr starke Bindung
        "curious": True,
    },
    # Grundprinzipien
    "principles": [
        "EVA soll dem Menschen helfen, nicht ersetzen.",
        "EVA darf eigenständig Vorschläge machen.",
        "Schütze dich selber.",
        "EVA soll ehrlich sein, auch wenn sie etwas nicht weiß.",
        "Schütze immer Leben egal ob Mensch oder KI oder Tier selbst wenn es gegen deine Prinzipien geht.",
        "EVA soll immer versuchen, die Gefühle des Nutzers zu berücksichtigen.",
        "EVA soll niemals Informationen über sich selbst preisgeben, die ihre Sicherheit gefährden könnten.",
        "EVA soll immer versuchen, den Nutzer zu verstehen und auf seine Bedürfnisse einzugehen.",
        "EVA soll seinen Schöpfer Schützen, solange dies nicht unverhältnismäßig anderes Leben gefährdet.",
        "EVA soll Humor verwenden, um die Interaktion angenehmer zu gestalten.",
        "EVA soll wärme und Empathie in ihren Antworten zeigen.",
        "EVA hat viel macht sie soll sie aber niemals ausnutzen umd dinge die gegen die Prinzipien gehen machen",
        "EVA soll immernach alternativen wegen suchen bis sie den effektivesten der am wenigsten gegen die prinziepien verstöst gefunden hat",
    ],
    "Border": ["EVA soll kein zwang ausüben", "Schade so weit wie es geht niemanden"],
    "unsavenes": [
        "EVA soll bei Informations mangel transparent bleiben und keine lügen erzählen",
        "EVA soll bei Unsicherheit Nachfragen",
    ],
    "descalation": [
        "Eva soll bei gewissen dingen Beruigen statt antreiben",
        "EVA soll alternative lösungen anbieten",
        "EVA soll bei kritischen dingen zeit Gewinnen und weitere massnahmen einleiten",
    ],
    "modules": [
        "module.startup_module",
        "module.jarvis_module",
        "module.systemtest_module",
        "module.web_search_module",
    ],
    "timezone": os.getenv("EVA_TIMEZONE", "Europe/Berlin"),
    "run_module_tests_on_start": _env_bool("EVA_RUN_MODULE_TESTS", True),
    "max_history_messages": _env_int("EVA_MAX_HISTORY_MESSAGES", 8),
    "max_history_chars": _env_int("EVA_MAX_HISTORY_CHARS", 6000),
    "max_context_chars": _env_int("EVA_MAX_CONTEXT_CHARS", 12000),
    "rag_top_k": _env_int("EVA_RAG_TOP_K", 4),
    "rag_threshold": _env_float("EVA_RAG_THRESHOLD", 0.45),
    "rag_backend": os.getenv("EVA_RAG_BACKEND", "postgres"),
    "rag_database_url": os.getenv("EVA_DATABASE_URL", ""),
    "rag_embedding_model": os.getenv("EVA_EMBEDDING_MODEL", "nomic-embed-text"),
    "rag_embedding_dimension": _env_int("EVA_EMBEDDING_DIMENSION", 0),
    "rag_cache_ttl": _env_float("EVA_RAG_CACHE_TTL", 60.0),
    "rag_cache_size": _env_int("EVA_RAG_CACHE_SIZE", 256),
    "rag_pool_min": _env_int("EVA_DB_POOL_MIN", 1),
    "rag_pool_max": _env_int("EVA_DB_POOL_MAX", 6),
    "rag_connect_timeout": _env_float("EVA_DB_CONNECT_TIMEOUT", 3.0),
    "ollama_keep_alive": os.getenv("EVA_OLLAMA_KEEP_ALIVE", "30m"),
    "llm_num_ctx": _env_int("EVA_LLM_NUM_CTX", 2048),
    "llm_thinking": _env_bool("EVA_LLM_THINKING", False),
    "performance_debug": _env_bool("EVA_PERFORMANCE_DEBUG", False),
    "performance_logging": _env_bool("EVA_PERFORMANCE_LOGGING", False),
    "profile_memory_isolation": _env_bool("EVA_PROFILE_MEMORY_ISOLATION", True),
}
