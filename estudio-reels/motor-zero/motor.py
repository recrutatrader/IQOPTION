#!/usr/bin/env python3
"""Motor Zero do Estúdio de Reels "O Poder da Mente Sábia".

Monta um reel vertical (1080x1920, 30 fps) a partir de projetos/<pasta>/roteiro.json usando
só ferramentas gratuitas: vídeos reais do Pexels e do Pixabay, voz neural do Edge (edge-tts),
legendas queimadas e o logo oficial sem alteração, tudo juntado pelo FFmpeg.

Uso:
  python motor-zero/motor.py verificar
  python motor-zero/motor.py voz projetos/<pasta>      só a narração: confere a duração
  python motor-zero/motor.py montar projetos/<pasta>   do roteiro ao reel.mp4 pronto
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import wave
from dataclasses import asdict, dataclass
from pathlib import Path

ESTUDIO = Path(__file__).resolve().parent.parent
MARCA = ESTUDIO / "marca"
FONTES = MARCA / "fontes"
TRILHAS = ESTUDIO / "trilhas"

LARGURA, ALTURA, FPS = 1080, 1920, 30
TAXA_AUDIO = 48000
CAUDA_S = 1.2  # respiro depois da última palavra
UA = {"User-Agent": "EstudioReels/1.0 (+https://opoderdamentesabia.com.br)"}
EXTENSOES_AUDIO = {".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac"}
COR_709 = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
           "-color_range", "tv"]

PADRAO = {
    "voz": "pt-BR-AntonioNeural",
    "velocidade_voz": "-4%",
    "tom_voz": "+0Hz",
    "pausa_entre_cenas_s": 0.3,
    "duracao_min_s": 60,
    "duracao_max_s": 180,
    "plano_max_s": 5.0,
    "logo": {
        "arquivo": "logo.png",
        "posicao": "topo-centro",
        "largura_max_px": 240,
        "margem_topo_px": 150,
        "margem_base_px": 150,
        "margem_lateral_px": 60,
    },
    "legenda": {
        "fonte": "Montserrat ExtraBold",
        "tamanho": 72,
        "cor": "#FFFFFF",
        "cor_destaque": "#F2C14E",
        "destacar_palavra": True,
        "cor_contorno": "#000000",
        "contorno": 6,
        "sombra": 2,
        "maiusculas": False,
        "palavras_por_bloco": 4,
        "letras_por_bloco": 24,
        "altura_da_base_px": 560,
    },
    "trilha": {"arquivo": "auto", "volume": 0.08},
}


class Erro(Exception):
    """Problema que o agente precisa resolver. A mensagem já diz o que fazer."""


class DuracaoForaDoLimite(Erro):
    pass


# --------------------------------------------------------------------------- utilidades

def rodar(cmd: list, cwd: Path | None = None) -> str:
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise Erro(f"Falha ao rodar {Path(str(cmd[0])).name}:\n{r.stderr[-2000:]}")
    return r.stdout


def sondar(arq: Path) -> dict:
    saida = rodar(["ffprobe", "-v", "error", "-show_entries",
                   "format=duration:stream=codec_type,width,height", "-of", "json", arq])
    return json.loads(saida)


def duracao(arq: Path) -> float:
    return float(sondar(arq)["format"].get("duration") or 0)


def dimensoes(arq: Path) -> tuple[int, int]:
    for s in sondar(arq).get("streams", []):
        if s.get("codec_type") == "video":
            return int(s["width"]), int(s["height"])
    raise Erro(f"{arq.name} não tem imagem.")


def duracao_wav(arq: Path) -> float:
    with wave.open(str(arq), "rb") as w:
        return w.getnframes() / w.getframerate()


def mesclar(base: dict, extra: dict) -> dict:
    saida = dict(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(saida.get(k), dict):
            saida[k] = mesclar(saida[k], v)
        else:
            saida[k] = v
    return saida


def carregar_config() -> dict:
    arq = MARCA / "config.json"
    if not arq.exists():
        return PADRAO
    return mesclar(PADRAO, json.loads(arq.read_text(encoding="utf-8")))


def carregar_env() -> None:
    arq = ESTUDIO / ".env"
    if not arq.exists():
        return
    for linha in arq.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            k, v = linha.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def cor_ass(hexa: str, alfa: int = 0) -> str:
    hexa = hexa.lstrip("#")
    r, g, b = hexa[0:2], hexa[2:4], hexa[4:6]
    return f"&H{alfa:02X}{b}{g}{r}".upper()


def tempo_ass(t: float) -> str:
    cs = max(0, round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def tempo_srt(t: float) -> str:
    ms = max(0, round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def caminho_filtro(destino: Path, origem: Path) -> str:
    """Caminho relativo com barras normais, para usar dentro de filtros do FFmpeg."""
    return os.path.relpath(destino, origem).replace("\\", "/")


# --------------------------------------------------------------------------- logo oficial

def conferir_logo(cfg: dict) -> Path:
    """O logo nunca é editado. O arquivo é só lido, e a impressão digital trava qualquer troca."""
    arq = MARCA / cfg["logo"]["arquivo"]
    if not arq.exists():
        raise Erro("Logo oficial não encontrado em marca/" + cfg["logo"]["arquivo"] + ". "
                   "Peça ao usuário o arquivo oficial e salve exatamente como veio. "
                   "Nunca crie, desenhe, gere ou substitua o logo.")
    soma = hashlib.sha256(arq.read_bytes()).hexdigest()
    trava = MARCA / "logo.sha256"
    if trava.exists():
        if trava.read_text(encoding="utf-8").split()[0] != soma:
            raise Erro("O arquivo do logo oficial é diferente do registrado em marca/logo.sha256. "
                       "Nenhum vídeo será montado. Se o dono da marca trocou o logo de propósito, "
                       "ele mesmo apaga marca/logo.sha256 e roda de novo.")
    else:
        trava.write_text(f"{soma}  {arq.name}\n", encoding="utf-8")
        print("Logo oficial registrado: impressão digital salva em marca/logo.sha256.")
    return arq


# --------------------------------------------------------------------------- roteiro

def ler_roteiro(proj: Path) -> dict:
    arq = proj / "roteiro.json"
    if not arq.exists():
        raise Erro(f"Não achei {arq}. Crie o roteiro primeiro.")
    try:
        rot = json.loads(arq.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise Erro(f"roteiro.json inválido: {e}") from e
    cenas = rot.get("cenas")
    if not rot.get("titulo") or not isinstance(cenas, list) or not cenas:
        raise Erro("O roteiro precisa de 'titulo' e de uma lista 'cenas'.")
    for i, c in enumerate(cenas, 1):
        if not str(c.get("texto", "")).strip():
            raise Erro(f"Cena {i} sem 'texto'.")
        busca = c.get("busca")
        if not c.get("videos") and (not isinstance(busca, list) or not busca):
            raise Erro(f"Cena {i} sem 'busca' (termos em inglês para achar os vídeos).")
    return rot


# --------------------------------------------------------------------------- voz

def _norm(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum())


async def _falar(texto: str, voz: str, vel: str, tom: str, destino: Path) -> list[dict]:
    import edge_tts

    try:
        com = edge_tts.Communicate(texto, voz, rate=vel, pitch=tom, boundary="WordBoundary")
    except TypeError:  # edge-tts antigo, que só manda palavras
        com = edge_tts.Communicate(texto, voz, rate=vel, pitch=tom)
    marcas = []
    with open(destino, "wb") as f:
        async for parte in com.stream():
            if parte["type"] == "audio":
                f.write(parte["data"])
            elif parte["type"] == "WordBoundary":
                ini = parte["offset"] / 1e7
                marcas.append({"ini": ini, "fim": ini + parte["duration"] / 1e7, "txt": parte["text"]})
    return marcas


def falar(texto: str, voz: str, vel: str, tom: str, destino: Path) -> list[dict]:
    ultimo = None
    for _ in range(3):
        try:
            return asyncio.run(_falar(texto, voz, vel, tom, destino))
        except Exception as e:  # rede instável: tenta de novo
            ultimo = e
    raise Erro(f"A voz não foi gerada ({voz}): {ultimo}. Confira a internet e o nome da voz.")


def alinhar(texto: str, marcas: list[dict], dur: float) -> list[dict]:
    """Casa as palavras faladas com as palavras do roteiro, mantendo acentos e pontuação."""
    tokens = [(t, _norm(t)) for t in texto.split()]
    if not marcas:  # sem marcação de palavras: distribui pelo tamanho
        total = sum(len(t) + 1 for t, _ in tokens) or 1
        t0, saida = 0.1, []
        for t, _ in tokens:
            d = (dur - 0.2) * (len(t) + 1) / total
            saida.append({"ini": t0, "fim": t0 + d, "txt": t})
            t0 += d
        return saida

    saida: list[dict] = []
    j, resto = 0, ""
    for m in marcas:
        nm = _norm(m["txt"])
        if not nm:
            continue
        if resto and resto.startswith(nm):  # pedaço de palavra com hífen
            resto = resto[len(nm):]
            saida[-1]["fim"] = m["fim"]
            continue
        resto = ""
        achou = None
        for k in range(j, min(j + 4, len(tokens))):
            nt = tokens[k][1]
            if nt and (nt.startswith(nm) or nm.startswith(nt)):
                achou = k
                break
        if achou is None:
            if j < len(tokens):  # falado diferente do escrito (ex.: números)
                saida.append({"ini": m["ini"], "fim": m["fim"], "txt": tokens[j][0]})
                j += 1
            continue
        txt = " ".join(t for t, _ in tokens[j:achou + 1])
        nt = tokens[achou][1]
        resto = nt[len(nm):] if nt.startswith(nm) else ""
        saida.append({"ini": m["ini"], "fim": m["fim"], "txt": txt})
        j = achou + 1
    if j < len(tokens) and saida:
        saida[-1]["txt"] += " " + " ".join(t for t, _ in tokens[j:])
    return saida


def gerar_voz(proj: Path, rot: dict, cfg: dict) -> dict:
    pasta = proj / "audio"
    pasta.mkdir(exist_ok=True)
    voz = rot.get("voz") or cfg["voz"]
    vel = rot.get("velocidade_voz") or cfg["velocidade_voz"]
    tom = rot.get("tom_voz") or cfg["tom_voz"]
    if not re.fullmatch(r"[+-]\d+%", vel) or not re.fullmatch(r"[+-]\d+Hz", tom):
        raise Erro("Use velocidade como '-5%' ou '+0%' e tom como '+0Hz' ou '-2Hz'.")
    pausa = float(cfg["pausa_entre_cenas_s"])
    cenas = rot["cenas"]

    info, t = [], 0.0
    for i, cena in enumerate(cenas, 1):
        texto = " ".join(str(cena["texto"]).split())
        chave = hashlib.sha1(json.dumps([texto, voz, vel, tom]).encode()).hexdigest()
        mp3, wav, meta_arq = (pasta / f"cena{i:02d}{ext}" for ext in (".mp3", ".wav", ".json"))
        meta = json.loads(meta_arq.read_text(encoding="utf-8")) if meta_arq.exists() else {}
        if meta.get("chave") != chave or not wav.exists():
            print(f"  voz da cena {i}/{len(cenas)}...")
            marcas = falar(texto, voz, vel, tom, mp3)
            rodar(["ffmpeg", "-y", "-v", "error", "-i", mp3, "-ar", TAXA_AUDIO, "-ac", 1, wav])
            meta = {"chave": chave, "marcas": marcas}
            meta_arq.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        fala = duracao_wav(wav)
        dur = fala + (pausa if i < len(cenas) else CAUDA_S)
        palavras = [{**p, "ini": p["ini"] + t, "fim": p["fim"] + t}
                    for p in alinhar(texto, meta["marcas"], fala)]
        info.append({"ini": t, "dur": dur, "fala": fala, "wav": wav, "palavras": palavras})
        t += dur

    with wave.open(str(proj / "narracao.wav"), "wb") as saida:
        saida.setnchannels(1)
        saida.setsampwidth(2)
        saida.setframerate(TAXA_AUDIO)
        for c in info:
            with wave.open(str(c["wav"]), "rb") as w:
                saida.writeframes(w.readframes(w.getnframes()))
            saida.writeframes(b"\0\0" * round((c["dur"] - c["fala"]) * TAXA_AUDIO))
    return {"total": t, "cenas": info, "voz": voz}


def checar_duracao(voz: dict, cfg: dict) -> None:
    total, minimo, maximo = voz["total"], cfg["duracao_min_s"], cfg["duracao_max_s"]
    palavras = sum(len(c["palavras"]) for c in voz["cenas"])
    por_seg = palavras / total if total else 2.4
    if total < minimo:
        falta = math.ceil((minimo + 5 - total) * por_seg)
        raise DuracaoForaDoLimite(f"Narração com {total:.0f} s: abaixo do mínimo de {minimo} s. "
                                  f"Acrescente cerca de {falta} palavras ao roteiro.")
    if total > maximo:
        sobra = math.ceil((total - maximo + 5) * por_seg)
        raise DuracaoForaDoLimite(f"Narração com {total:.0f} s: acima do máximo de {maximo} s. "
                                  f"Corte cerca de {sobra} palavras do roteiro.")


# --------------------------------------------------------------------------- legendas

def preparar_palavras(voz: dict, cfg_leg: dict) -> list[dict]:
    saida = []
    for c in voz["cenas"]:
        for p in c["palavras"]:
            bruto = p["txt"].strip()
            limpo = bruto.strip("\"'“”‘’()[]«»").rstrip(".,;:…")
            if not limpo:
                continue
            fim_txt = bruto.rstrip("\"'“”’)]»")
            saida.append({
                "ini": p["ini"], "fim": p["fim"],
                "exib": limpo.upper() if cfg_leg["maiusculas"] else limpo,
                "fim_frase": fim_txt.endswith((".", "?", "!", "…", ":", ";")),
                "virgula": fim_txt.endswith(","),
            })
    return saida


def montar_blocos(palavras: list[dict], cfg_leg: dict) -> list[dict]:
    maxp, maxc = cfg_leg["palavras_por_bloco"], cfg_leg["letras_por_bloco"]
    blocos, atual = [], []
    for i, p in enumerate(palavras):
        atual.append(p)
        letras = len(" ".join(x["exib"] for x in atual))
        prox = palavras[i + 1] if i + 1 < len(palavras) else None
        fecha = (prox is None or len(atual) >= maxp or letras >= maxc or p["fim_frase"]
                 or (p["virgula"] and len(atual) >= 2) or prox["ini"] - p["fim"] > 0.6
                 or letras + 1 + len(prox["exib"]) > maxc + 6)
        if fecha:
            blocos.append({"palavras": atual})
            atual = []
    for i, b in enumerate(blocos):
        b["ini"] = b["palavras"][0]["ini"]
        fim_fala = b["palavras"][-1]["fim"]
        if i + 1 < len(blocos):
            prox = blocos[i + 1]["palavras"][0]["ini"]
            b["fim"] = prox if prox - fim_fala < 0.5 else fim_fala + 0.4
        else:
            b["fim"] = fim_fala + 0.6
    return blocos


def _texto_ass(s: str) -> str:
    return s.replace("\\", "").replace("{", "(").replace("}", ")")


def escrever_legendas(proj: Path, blocos: list[dict], cfg_leg: dict) -> None:
    estilo = ",".join(str(x) for x in [
        "Legenda", cfg_leg["fonte"], cfg_leg["tamanho"], cor_ass(cfg_leg["cor"]),
        cor_ass(cfg_leg["cor"]), cor_ass(cfg_leg["cor_contorno"]), cor_ass("#000000", 0x60),
        0, 0, 0, 0, 100, 100, 0, 0, 1, cfg_leg["contorno"], cfg_leg["sombra"], 2,
        80, 80, cfg_leg["altura_da_base_px"], 1])
    linhas = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {LARGURA}", f"PlayResY: {ALTURA}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: {estilo}", "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    destaque = cor_ass(cfg_leg["cor_destaque"])
    srt = []
    for n, b in enumerate(blocos, 1):
        pals = [_texto_ass(p["exib"]) for p in b["palavras"]]
        srt += [str(n), f"{tempo_srt(b['ini'])} --> {tempo_srt(b['fim'])}",
                " ".join(p["exib"] for p in b["palavras"]), ""]
        if not cfg_leg["destacar_palavra"]:
            linhas.append(f"Dialogue: 0,{tempo_ass(b['ini'])},{tempo_ass(b['fim'])},"
                          f"Legenda,,0,0,0,,{' '.join(pals)}")
            continue
        for k, p in enumerate(b["palavras"]):
            ini = b["ini"] if k == 0 else p["ini"]
            fim = b["palavras"][k + 1]["ini"] if k + 1 < len(pals) else b["fim"]
            fim = max(fim, ini + 0.05)
            texto = " ".join(f"{{\\1c{destaque}&}}{w}{{\\r}}" if j == k else w
                             for j, w in enumerate(pals))
            linhas.append(f"Dialogue: 0,{tempo_ass(ini)},{tempo_ass(fim)},Legenda,,0,0,0,,{texto}")
    (proj / "legendas.ass").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    (proj / "legendas.srt").write_text("\n".join(srt), encoding="utf-8")


# --------------------------------------------------------------------------- vídeos gratuitos

@dataclass
class Clipe:
    fonte: str
    id: str
    url: str
    dur: float
    w: int
    h: int
    autor: str
    pagina: str

    @property
    def chave(self) -> str:
        return f"{self.fonte}:{self.id}"

    def nota(self) -> int:
        """Menor é melhor. 9 = qualidade baixa demais para 1080x1920."""
        if self.h >= self.w:
            return 0 if self.w >= 1080 else 1 if self.w >= 720 else 9
        return 2 if self.h >= 2160 else 4 if self.h >= 1080 else 9


def _melhor_arquivo(arquivos: list[tuple[str, int, int]]):
    validos = [a for a in arquivos if a[0] and a[1] and a[2]]
    if not validos:
        return None

    def custo(a):
        _, w, h = a
        lado, alvo = (w, 1080) if h >= w else (h, 2160)
        return (0 if lado >= alvo else 1, abs(lado - alvo))

    return min(validos, key=custo)


class Acervo:
    """Busca vídeos reais gratuitos no Pexels e no Pixabay, com cache das buscas."""

    def __init__(self, proj: Path):
        import requests

        self.http = requests.Session()
        self.http.headers.update(UA)
        self.pexels = os.environ.get("PEXELS_API_KEY", "").strip()
        self.pixabay = os.environ.get("PIXABAY_API_KEY", "").strip()
        if not self.pexels and not self.pixabay:
            raise Erro("Sem chave de vídeos grátis. Coloque PEXELS_API_KEY e/ou PIXABAY_API_KEY "
                       "no arquivo .env do estúdio (as duas são gratuitas).")
        self.pasta = proj / "clipes"
        self.pasta.mkdir(exist_ok=True)
        self.cache_arq = self.pasta / "buscas.json"
        self.cache = (json.loads(self.cache_arq.read_text(encoding="utf-8"))
                      if self.cache_arq.exists() else {})

    def _salvar_cache(self) -> None:
        self.cache_arq.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")

    def _get(self, url: str, **kw) -> dict:
        r = self.http.get(url, timeout=30, **kw)
        if r.status_code in (401, 403):
            raise Erro(f"Chave recusada por {url.split('/')[2]}. Confira o .env.")
        r.raise_for_status()
        return r.json()

    def _de_pexels(self, v: dict) -> Clipe | None:
        arqs = [(f.get("link"), f.get("width"), f.get("height")) for f in v.get("video_files", [])
                if f.get("file_type") == "video/mp4"]
        melhor = _melhor_arquivo(arqs)
        if not melhor:
            return None
        return Clipe("pexels", str(v["id"]), melhor[0], float(v.get("duration") or 0),
                     melhor[1], melhor[2], v.get("user", {}).get("name", ""), v.get("url", ""))

    def _de_pixabay(self, hit: dict) -> Clipe | None:
        vs = hit.get("videos", {})
        arqs = [(vs[k].get("url"), vs[k].get("width"), vs[k].get("height"))
                for k in ("large", "medium", "small") if k in vs]
        melhor = _melhor_arquivo(arqs)
        if not melhor:
            return None
        return Clipe("pixabay", str(hit["id"]), melhor[0], float(hit.get("duration") or 0),
                     melhor[1], melhor[2], hit.get("user", ""), hit.get("pageURL", ""))

    def buscar(self, termo: str) -> list[Clipe]:
        resultado = []
        if self.pexels:
            chave = f"pexels|{termo}"
            if chave not in self.cache:
                dados = self._get("https://api.pexels.com/videos/search",
                                  params={"query": termo, "orientation": "portrait", "per_page": 20},
                                  headers={"Authorization": self.pexels})
                self.cache[chave] = [asdict(c) for c in map(self._de_pexels, dados.get("videos", [])) if c]
                self._salvar_cache()
            resultado += [Clipe(**c) for c in self.cache[chave]]
        if self.pixabay:
            chave = f"pixabay|{termo}"
            if chave not in self.cache:
                dados = self._get("https://pixabay.com/api/videos/",
                                  params={"key": self.pixabay, "q": termo[:100], "per_page": 20,
                                          "safesearch": "true"})
                self.cache[chave] = [asdict(c) for c in map(self._de_pixabay, dados.get("hits", [])) if c]
                self._salvar_cache()
            resultado += [Clipe(**c) for c in self.cache[chave]]
        return sorted(resultado, key=Clipe.nota)  # sorted é estável: mantém a relevância

    def por_id(self, chave: str) -> Clipe | None:
        fonte, _, vid = chave.partition(":")
        if fonte == "pexels" and self.pexels:
            v = self._get(f"https://api.pexels.com/videos/videos/{vid}",
                          headers={"Authorization": self.pexels})
            return self._de_pexels(v)
        if fonte == "pixabay" and self.pixabay:
            hits = self._get("https://pixabay.com/api/videos/",
                             params={"key": self.pixabay, "id": vid}).get("hits", [])
            return self._de_pixabay(hits[0]) if hits else None
        return None

    def baixar(self, c: Clipe) -> Path:
        destino = self.pasta / f"{c.fonte}-{c.id}.mp4"
        if destino.exists() and destino.stat().st_size > 0:
            return destino
        print(f"  baixando {c.chave} ({c.w}x{c.h})...")
        parte = destino.with_suffix(".part")
        with self.http.get(c.url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(parte, "wb") as f:
                for bloco in r.iter_content(1 << 20):
                    f.write(bloco)
        parte.replace(destino)
        return destino


def escolher_planos(rot: dict, voz: dict, cfg: dict, acervo: Acervo) -> list[dict]:
    usados: set[str] = set()
    planos = []
    for i, (cena, info) in enumerate(zip(rot["cenas"], voz["cenas"]), 1):
        evitar = set(cena.get("evitar", []))
        dur = info["dur"]
        n_ideal = max(1, math.ceil(dur / float(cfg["plano_max_s"])))
        candidatos: list[Clipe] = []
        vistos: set[str] = set()

        def juntar(lista):
            for c in lista:
                if c and c.chave not in vistos and c.chave not in usados \
                        and c.chave not in evitar and c.nota() < 9:
                    vistos.add(c.chave)
                    candidatos.append(c)

        juntar(acervo.por_id(k) for k in cena.get("videos", []))
        for termo in cena.get("busca", []):
            if sum(1 for c in candidatos if c.dur >= dur / n_ideal + 0.5) >= n_ideal + 2:
                break
            juntar(acervo.buscar(termo))

        escolhidos = []
        for n in range(n_ideal, 0, -1):
            escolhidos = [c for c in candidatos if c.dur >= dur / n + 0.4][:n]
            if len(escolhidos) == n:
                break
        if not escolhidos:
            raise Erro(f"Cena {i}: não achei vídeos gratuitos longos o bastante "
                       f"({dur:.1f} s). Troque ou acrescente termos em 'busca', ou divida a cena.")
        t = info["ini"]
        passo = dur / len(escolhidos)
        for k, c in enumerate(escolhidos):
            usados.add(c.chave)
            fim = info["ini"] + dur if k == len(escolhidos) - 1 else t + passo
            planos.append({"cena": i, "ini": t, "fim": fim, "clipe": c})
            t = fim
    return planos


def renderizar_planos(proj: Path, planos: list[dict], acervo: Acervo) -> Path:
    pasta = proj / "planos"
    if pasta.exists():
        shutil.rmtree(pasta)
    pasta.mkdir()
    vf = (f"scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase:flags=lanczos,"
          f"crop={LARGURA}:{ALTURA},setsar=1,fps={FPS},format=yuv420p,"
          f"tpad=stop_mode=clone:stop_duration=3")
    lista = []
    for n, p in enumerate(planos, 1):
        arq = acervo.baixar(p["clipe"])
        real = duracao(arq)
        p["arquivo"] = arq
        quadros = round(p["fim"] * FPS) - round(p["ini"] * FPS)
        precisa = quadros / FPS
        inicio = max(0.0, min(2.0, (real - precisa) / 2))
        saida = pasta / f"p{n:03d}.mp4"
        print(f"  plano {n}/{len(planos)}: cena {p['cena']}, {precisa:.1f} s de {p['clipe'].chave}")
        rodar(["ffmpeg", "-y", "-v", "error", "-ss", f"{inicio:.3f}", "-i", arq, "-vf", vf,
               "-frames:v", quadros, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", 18,
               "-r", FPS, *COR_709, saida])
        lista.append(f"file '{saida.name}'")
    (pasta / "lista.txt").write_text("\n".join(lista) + "\n", encoding="utf-8")
    video = proj / "video.mp4"
    rodar(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", 0, "-i", pasta / "lista.txt",
           "-c", "copy", video])
    return video


def montar_previa(proj: Path, planos: list[dict]) -> None:
    """Folha de contato: um quadro do meio de cada plano, numerado, para revisar as imagens."""
    pasta = proj / "planos" / "previa"
    pasta.mkdir(exist_ok=True)
    fonte = caminho_filtro(FONTES / "Montserrat-ExtraBold.ttf", proj)
    for n, p in enumerate(planos, 1):
        meio = (p["ini"] + p["fim"]) / 2
        rodar(["ffmpeg", "-y", "-v", "error", "-ss", f"{meio:.2f}", "-i", "video.mp4",
               "-frames:v", 1, "-update", 1, "-vf",
               f"scale=216:384,drawtext=fontfile={fonte}:text={n}:x=10:y=8:fontsize=36:"
               f"fontcolor=white:borderw=3:bordercolor=black",
               f"planos/previa/{n:03d}.jpg"], cwd=proj)
    colunas = 6
    linhas = math.ceil(len(planos) / colunas)
    rodar(["ffmpeg", "-y", "-v", "error", "-framerate", 1, "-i", "planos/previa/%03d.jpg",
           "-vf", f"tile={colunas}x{linhas}:padding=6:margin=6:color=white", "-frames:v", 1,
           "-update", 1, "-q:v", 3, "previa.jpg"], cwd=proj)


# --------------------------------------------------------------------------- montagem final

def escolher_trilha(rot: dict, cfg: dict) -> Path | None:
    pedido = rot.get("trilha", cfg["trilha"]["arquivo"])
    if not pedido or pedido == "nenhuma":
        return None
    if pedido != "auto":
        arq = TRILHAS / pedido
        if not arq.exists():
            raise Erro(f"Trilha {pedido} não está na pasta trilhas/.")
        return arq
    opcoes = sorted(a for a in TRILHAS.iterdir() if a.suffix.lower() in EXTENSOES_AUDIO) \
        if TRILHAS.exists() else []
    if not opcoes:
        return None
    return opcoes[int(hashlib.sha1(rot["titulo"].encode()).hexdigest(), 16) % len(opcoes)]


def montar_final(proj: Path, total: float, logo: Path, trilha: Path | None, cfg: dict) -> Path:
    lg = cfg["logo"]
    w, _ = dimensoes(logo)
    # Único ajuste permitido no logo: tamanho proporcional (nunca recorta, recolore ou distorce).
    tamanho = f",scale={lg['largura_max_px']}:-1:flags=lanczos" if w > lg["largura_max_px"] else ""
    x_meio, x_esq = "(main_w-overlay_w)/2", str(lg["margem_lateral_px"])
    x_dir = f"main_w-overlay_w-{lg['margem_lateral_px']}"
    y_topo, y_base = str(lg["margem_topo_px"]), f"main_h-overlay_h-{lg['margem_base_px']}"
    pos = {
        "topo-centro": (x_meio, y_topo), "topo-esquerda": (x_esq, y_topo),
        "topo-direita": (x_dir, y_topo), "base-centro": (x_meio, y_base),
        "base-esquerda": (x_esq, y_base), "base-direita": (x_dir, y_base),
    }
    if lg["posicao"] not in pos:
        raise Erro(f"Posição do logo inválida: {lg['posicao']}. Use uma de: {', '.join(pos)}.")
    x, y = pos[lg["posicao"]]

    fontes = caminho_filtro(FONTES, proj)
    # O logo passa para vídeo na mesma matriz de cor (BT.709) com que o reel é marcado,
    # para as cores saírem iguais às do arquivo oficial.
    filtro = [
        f"[0:v]subtitles=legendas.ass:fontsdir={fontes},format=yuv444p[leg]",
        f"[2:v]format=rgba{tamanho},scale=out_color_matrix=bt709:out_range=tv,format=yuva444p[logo]",
        f"[leg][logo]overlay=x={x}:y={y}:format=yuv444:eof_action=repeat,format=yuv420p[v]",
    ]
    entradas = ["-i", "video.mp4", "-i", "narracao.wav", "-i", logo]
    normalizar = "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000"
    if trilha:
        entradas += ["-stream_loop", -1, "-i", trilha]
        vol = cfg["trilha"]["volume"]
        filtro += [f"[3:a]volume={vol},afade=t=out:st={max(0, total - 2.5):.2f}:d=2.5[mus]",
                   f"[1:a][mus]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
                   f"{normalizar}[a]"]
    else:
        filtro.append(f"[1:a]{normalizar}[a]")

    saida = proj / "reel.mp4"
    print("  montagem final (legendas, logo, áudio)...")
    rodar(["ffmpeg", "-y", "-v", "error", *entradas, "-filter_complex", ";".join(filtro),
           "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}", "-r", FPS,
           "-c:v", "libx264", "-preset", "medium", "-crf", 20, "-profile:v", "high",
           "-pix_fmt", "yuv420p", *COR_709, "-c:a", "aac", "-b:a", "192k", "-ar", TAXA_AUDIO,
           "-movflags", "+faststart", saida.name], cwd=proj)
    rodar(["ffmpeg", "-y", "-v", "error", "-ss", 1.5, "-i", saida.name, "-frames:v", 1,
           "-update", 1, "-q:v", 2, "capa.jpg"], cwd=proj)
    return saida


def escrever_textos(proj: Path, rot: dict, planos: list[dict], voz: dict) -> None:
    hashtags = " ".join(rot.get("hashtags", []))
    post = "\n\n".join(x for x in [rot["titulo"], rot.get("legenda_post", "").strip(), hashtags] if x)
    (proj / "post.txt").write_text(post + "\n", encoding="utf-8")

    vistos, creditos = set(), ["Vídeos gratuitos usados neste reel (licenças Pexels/Pixabay):"]
    for p in planos:
        c = p["clipe"]
        if c.chave not in vistos:
            vistos.add(c.chave)
            creditos.append(f"- {c.fonte.capitalize()} {c.id}, por {c.autor or 'autor não informado'}: {c.pagina}")
    creditos.append(f"\nNarração: voz neural {voz['voz']} (Microsoft Edge, via edge-tts).")
    (proj / "creditos.txt").write_text("\n".join(creditos) + "\n", encoding="utf-8")

    roteiro_txt = [rot["titulo"], ""]
    for i, c in enumerate(rot["cenas"], 1):
        roteiro_txt.append(f"[Cena {i}] {' '.join(str(c['texto']).split())}")
    (proj / "roteiro.txt").write_text("\n".join(roteiro_txt) + "\n", encoding="utf-8")

    relatorio = {
        "titulo": rot["titulo"], "duracao_s": round(voz["total"], 2), "voz": voz["voz"],
        "planos": [{"n": n, "cena": p["cena"], "ini": round(p["ini"], 2), "fim": round(p["fim"], 2),
                    "video": p["clipe"].chave, "pagina": p["clipe"].pagina}
                   for n, p in enumerate(planos, 1)],
    }
    (proj / "relatorio.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=2),
                                         encoding="utf-8")


# --------------------------------------------------------------------------- comandos

def cmd_verificar() -> int:
    cfg = carregar_config()
    itens = []
    itens.append(("Python 3.9+", sys.version_info >= (3, 9), sys.version.split()[0]))
    for prog in ("ffmpeg", "ffprobe"):
        itens.append((prog, shutil.which(prog) is not None, "instale o FFmpeg"))
    for mod in ("edge_tts", "requests"):
        try:
            __import__(mod)
            itens.append((mod, True, ""))
        except ImportError:
            itens.append((mod, False, "rode: python -m pip install -r motor-zero/requirements.txt"))
    chaves = [k for k in ("PEXELS_API_KEY", "PIXABAY_API_KEY") if os.environ.get(k, "").strip()]
    itens.append(("chave de vídeos grátis (.env)", bool(chaves), ", ".join(chaves) or "nenhuma"))
    logo = MARCA / cfg["logo"]["arquivo"]
    itens.append((f"logo oficial (marca/{cfg['logo']['arquivo']})", logo.exists(),
                  "registrado" if (MARCA / "logo.sha256").exists() else "ainda não registrado"))
    itens.append(("fonte das legendas", (FONTES / "Montserrat-ExtraBold.ttf").exists(), ""))
    estilo = (MARCA / "estilo.md").read_text(encoding="utf-8") if (MARCA / "estilo.md").exists() else ""
    itens.append(("modelo estudado (marca/estilo.md)", "STATUS: PENDENTE" not in estilo,
                  "rode /estudar-modelo" if "STATUS: PENDENTE" in estilo else ""))
    trilhas = [a.name for a in TRILHAS.iterdir() if a.suffix.lower() in EXTENSOES_AUDIO] \
        if TRILHAS.exists() else []
    itens.append(("trilhas de fundo (opcional)", True, f"{len(trilhas)} arquivo(s)"))
    ok = True
    for nome, passou, obs in itens:
        ok &= passou
        print(f"[{'OK' if passou else 'FALTA'}] {nome}" + (f": {obs}" if obs else ""))
    return 0 if ok else 1


def cmd_voz(proj: Path) -> int:
    cfg = carregar_config()
    rot = ler_roteiro(proj)
    voz = gerar_voz(proj, rot, cfg)
    palavras = sum(len(c["palavras"]) for c in voz["cenas"])
    print(f"Narração: {voz['total']:.1f} s, {palavras} palavras, voz {voz['voz']}.")
    for i, c in enumerate(voz["cenas"], 1):
        print(f"  cena {i}: {c['dur']:.1f} s")
    checar_duracao(voz, cfg)
    print("Duração dentro do limite.")
    return 0


def cmd_montar(proj: Path) -> int:
    cfg = carregar_config()
    logo = conferir_logo(cfg)
    rot = ler_roteiro(proj)
    print("1/5 Voz")
    voz = gerar_voz(proj, rot, cfg)
    checar_duracao(voz, cfg)
    print("2/5 Legendas")
    blocos = montar_blocos(preparar_palavras(voz, cfg["legenda"]), cfg["legenda"])
    escrever_legendas(proj, blocos, cfg["legenda"])
    print("3/5 Vídeos gratuitos")
    acervo = Acervo(proj)
    planos = escolher_planos(rot, voz, cfg, acervo)
    renderizar_planos(proj, planos, acervo)
    montar_previa(proj, planos)
    print("4/5 Montagem")
    saida = montar_final(proj, voz["total"], logo, escolher_trilha(rot, cfg), cfg)
    print("5/5 Conferência")
    conferir_logo(cfg)
    escrever_textos(proj, rot, planos, voz)
    w, h = dimensoes(saida)
    d = duracao(saida)
    if not (cfg["duracao_min_s"] <= d <= cfg["duracao_max_s"] + 0.5) or (w, h) != (LARGURA, ALTURA):
        raise Erro(f"O vídeo final saiu com {d:.1f} s e {w}x{h}: fora do padrão.")
    print(f"\nPronto: {saida}\n  {w}x{h}, {d:.1f} s, {len(planos)} planos de vídeo real")
    print(f"  revise: previa.jpg (planos numerados), capa.jpg | publique com: post.txt")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    carregar_env()
    ap = argparse.ArgumentParser(description="Motor Zero: monta reels a partir do roteiro.")
    ap.add_argument("comando", choices=["verificar", "voz", "montar"])
    ap.add_argument("projeto", nargs="?", help="pasta do projeto, ex.: projetos/2026-10-03-gratidao")
    args = ap.parse_args()
    try:
        if args.comando == "verificar":
            return cmd_verificar()
        if not args.projeto:
            raise Erro("Informe a pasta do projeto, ex.: projetos/2026-10-03-gratidao")
        proj = Path(args.projeto).resolve()
        return cmd_voz(proj) if args.comando == "voz" else cmd_montar(proj)
    except DuracaoForaDoLimite as e:
        print(f"\nDURAÇÃO: {e}", file=sys.stderr)
        return 2
    except Erro as e:
        print(f"\nERRO: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
