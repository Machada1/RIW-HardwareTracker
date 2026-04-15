"""
Hardware Crawler — Processador de Texto (Fase 2: Representação)

Pipeline de pré-processamento para português brasileiro:
  1. Limpeza de HTML (BeautifulSoup)
  2. Tokenização por regex (\\w+)
  3. Lowercasing e remoção de tokens inválidos
  4. Remoção de stopwords PT-BR
  5. Stemming RSLP (NLTK) com fallback suffix-stripping

O RSLP (Removedor de Sufixos da Língua Portuguesa) é um algoritmo
desenvolvido especificamente para o português (Orengo & Huyck, 2001).
Quando não disponível (dados NLTK ausentes), usa-se suffix-stripping
heurístico como fallback.
"""

import re
import unicodedata
from typing import Optional


# ---------------------------------------------------------------------------
# Stopwords PT-BR
# Lista combinada: NLTK stopwords PT + termos de UI de e-commerce
# ---------------------------------------------------------------------------
_STOPWORDS_PT = {
    # Artigos
    "o", "a", "os", "as", "um", "uma", "uns", "umas",
    # Preposições
    "de", "da", "do", "das", "dos", "em", "na", "no", "nas", "nos",
    "por", "para", "com", "sem", "sob", "sobre", "até", "ate", "após", "apos",
    "ante", "entre", "contra", "desde", "durante", "perante", "mediante",
    "conforme", "segundo", "exceto", "salvo", "fora", "além", "alem",
    # Conjunções
    "e", "ou", "mas", "porém", "porem", "todavia", "contudo", "entretanto",
    "que", "se", "porque", "como", "quando", "enquanto", "embora", "pois",
    "logo", "portanto", "então", "entao",
    # Pronomes
    "eu", "tu", "ele", "ela", "nós", "nos", "vós", "vos", "eles", "elas",
    "me", "te", "se", "nos", "vos", "lhe", "lhes", "meu", "minha",
    "seu", "sua", "seus", "suas", "nosso", "nossa", "nossos", "nossas",
    "este", "esta", "estes", "estas", "esse", "essa", "esses", "essas",
    "aquele", "aquela", "aqueles", "aquelas", "isto", "isso", "aquilo",
    "tudo", "nada", "algo", "alguém", "alguem", "ninguém", "ninguem",
    # Verbos auxiliares comuns
    "é", "e", "são", "sao", "foi", "foram", "ser", "estar", "ter",
    "há", "ha", "tem", "têm", "tem", "tinha", "tinham", "pode", "podem",
    "deve", "devem", "vai", "vão", "vao",
    # Advérbios comuns
    "não", "nao", "sim", "já", "ja", "ainda", "sempre", "nunca", "talvez",
    "também", "tambem", "mais", "menos", "muito", "pouco", "bem", "mal",
    "aqui", "ali", "lá", "la", "agora", "antes", "depois", "sempre",
    "apenas", "somente", "só", "so", "até", "ate", "mesmo", "assim",
    # Números escritos
    "um", "dois", "três", "tres", "quatro", "cinco", "seis", "sete",
    "oito", "nove", "dez",
    # Termos genéricos de e-commerce (boilerplate)
    "ver", "mais", "comprar", "adicionar", "carrinho", "frete", "grátis",
    "gratis", "clique", "acesse", "confira", "disponível", "disponivel",
    "estoque", "parcelas", "parcelado", "avaliações", "avaliacoes",
    "voltar", "início", "inicio", "cadastro", "login", "conta", "minha",
    "departamento", "busca", "pesquisa", "resultado", "página", "pagina",
    "anterior", "próximo", "proximo",
}


def _normalize_unicode(text: str) -> str:
    """Remove diacríticos preservando letras base (para stemming)."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


class _FallbackStemmer:
    """
    Stemmer heurístico por suffix-stripping para português.

    Remove sufixos comuns de flexão (plural, gênero, tempo verbal).
    Não é tão preciso quanto o RSLP, mas funciona sem dados externos.
    """

    # Sufixos ordenados do mais longo ao mais curto
    _SUFFIXES = [
        "amentos", "imentos", "adores", "adoras", "ações", "acoes",
        "ências", "encias", "âncias", "ancias", "amento", "imento",
        "adores", "adoras", "ações", "ação", "acao", "ências", "ência",
        "encia", "ância", "ancia", "mente", "istas", "istas",
        "agens", "agem", "ando", "endo", "indo", "ável", "avel",
        "ível", "ivel", "dades", "dade", "istas", "ista",
        "ores", "oras", "ões", "oes", "ção", "cao", "ais", "eis",
        "uis", "mos", "des", "res", "ves", "les",
        "ada", "ado", "ida", "ido", "ara", "ará", "ara", "era",
        "erá", "era", "ira", "irá", "ira", "ava", "ia", "ar",
        "er", "ir", "ou", "eu",
        "as", "os", "es", "is", "us",
        "a", "o", "e",
    ]
    _MIN_STEM_LEN = 3

    def stem(self, word: str) -> str:
        for suffix in self._SUFFIXES:
            if word.endswith(suffix) and len(word) - len(suffix) >= self._MIN_STEM_LEN:
                return word[: len(word) - len(suffix)]
        return word


def _load_rslp():
    """Tenta carregar RSLPStemmer do NLTK. Retorna None se falhar."""
    try:
        from nltk.stem import RSLPStemmer
        s = RSLPStemmer()
        s.stem("processadores")  # trigger any lazy load
        return s
    except Exception:
        return None


def _load_nltk_stopwords():
    """Tenta carregar stopwords PT do NLTK. Retorna set vazio se falhar."""
    try:
        from nltk.corpus import stopwords
        return set(stopwords.words("portuguese"))
    except Exception:
        return set()


class TextProcessor:
    """
    Processador de texto para indexação em PT-BR.

    Uso:
        tp = TextProcessor()
        tokens = tp.process("Placa de Vídeo RTX 4070 com 12GB GDDR6X")
        # → ['plac', 'vid', 'rtx', '4070', 'gb', 'gddr6x']
    """

    # Mínimo de caracteres de um token para ser indexado
    MIN_TOKEN_LEN = 2
    # Máximo (evita strings gigantes, ex: base64 em scripts que escaparam)
    MAX_TOKEN_LEN = 40

    def __init__(self, use_stemming: bool = True, use_stopwords: bool = True):
        self.use_stemming = use_stemming
        self.use_stopwords = use_stopwords

        # Stopwords: NLTK + nossa lista customizada
        self._stopwords: set[str] = set()
        if use_stopwords:
            nltk_sw = _load_nltk_stopwords()
            self._stopwords = _STOPWORDS_PT | {_normalize_unicode(w) for w in nltk_sw}

        # Stemmer: RSLP preferido, fallback heurístico
        self._stemmer = None
        self._stemmer_name = "none"
        if use_stemming:
            rslp = _load_rslp()
            if rslp:
                self._stemmer = rslp
                self._stemmer_name = "rslp"
            else:
                self._stemmer = _FallbackStemmer()
                self._stemmer_name = "suffix-stripping"

    @property
    def stemmer_name(self) -> str:
        return self._stemmer_name

    def process(self, text: str) -> list[str]:
        """
        Converte texto bruto em lista de stems indexáveis.

        Passos: lowercasing → tokenização → filtro comprimento →
                normalização unicode → stopwords → stemming
        """
        if not text:
            return []

        text = text.lower()

        # Tokenização: só palavras (letras, dígitos, underscore)
        tokens = re.findall(r"\b\w+\b", text)

        result: list[str] = []
        for token in tokens:
            # Comprimento mínimo/máximo
            if len(token) < self.MIN_TOKEN_LEN or len(token) > self.MAX_TOKEN_LEN:
                continue

            # Tokens só-numéricos longos (IDs de produto) são úteis para busca exata
            # mas não contribuem para ranking — indexamos até 8 dígitos
            if token.isdigit() and len(token) > 8:
                continue

            # Normalizar unicode para comparação de stopwords
            normalized = _normalize_unicode(token)

            # Stopwords
            if self.use_stopwords and normalized in self._stopwords:
                continue

            # Stemming
            if self._stemmer:
                stem = _normalize_unicode(self._stemmer.stem(normalized))
            else:
                stem = normalized

            if len(stem) < self.MIN_TOKEN_LEN:
                continue

            result.append(stem)

        return result

    def process_query(self, query: str) -> list[str]:
        """Processa uma query de busca (mesmo pipeline do corpus)."""
        return self.process(query)
