import logging
from pathlib import Path

from processors.base import ProcessadorArquivo

logger = logging.getLogger(__name__)


class ProcessadorImagem(ProcessadorArquivo):
    extensoes_suportadas = [".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"]

    @classmethod
    def processar(cls, caminho: str | Path, base_dir: Path | None = None) -> str:
        from PIL import Image

        path = cls._validar_caminho(caminho, base_dir)
        img = Image.open(str(path))
        largura, altura = img.size
        formato = img.format or "Desconhecido"
        modo = img.mode

        info_parts = [
            f"Formato: {formato}",
            f"Dimensoes: {largura}x{altura}",
            f"Cores: {modo}",
            f"Tamanho: {path.stat().st_size / 1024:.1f} KB",
        ]

        tem_transparencia = modo in ("RGBA", "LA", "PA") or ("transparency" in img.info)
        if tem_transparencia:
            info_parts.append("Transparencia: Sim")

        try:
            exif = img._getexif()
            if exif:
                campos_relevantes = {
                    271: "Camera",
                    272: "Modelo",
                    306: "Data",
                    36867: "Data Original",
                }
                partes_exif = []
                for tag_id, nome in campos_relevantes.items():
                    if tag_id in exif:
                        partes_exif.append(f"{nome}: {exif[tag_id]}")
                if partes_exif:
                    info_parts.append("EXIF: " + " | ".join(partes_exif))
        except Exception as e:
            logger.debug("Failed to read EXIF metadata: %s", e)

        if img.mode in ("RGB", "RGBA"):
            try:
                img_mini = img.copy()
                img_mini.thumbnail((100, 100))
                pixels = list(img_mini.getdata())
                if pixels:
                    r_avg = sum(p[0] for p in pixels) // len(pixels)
                    g_avg = sum(p[1] for p in pixels) // len(pixels)
                    b_avg = sum(p[2] for p in pixels) // len(pixels)
                    info_parts.append(f"Cor media: rgb({r_avg},{g_avg},{b_avg})")
            except Exception as e:
                logger.debug("Failed to compute average color: %s", e)

        informacoes = " | ".join(info_parts)

        return (
            f"[Imagem: {path.name}]\n"
            f"{informacoes}\n"
            f"[Para analise visual completa, envie esta imagem diretamente ao modelo de visao]"
        )
