"""
deteccao_movimento_tempo_real.py  (PLANO B garantido — só OpenCV)
================================================================
Detecta violência pela INTUIÇÃO temporal: violência = movimento brusco e
intenso. Em vez de pose, mede DIRETAMENTE quanto a imagem muda de um quadro
pro outro (diferença de frames). Parado -> a tela quase não muda -> ~0%.
Soco/briga -> muita coisa muda de repente -> dispara.

Vantagem: usa SÓ OpenCV + NumPy (que já estão instalados), então roda em
qualquer Python — inclusive o 3.14, onde o MediaPipe não coopera.

>>> RODE NO WINDOWS <<<  (ou dê 2 cliques em rodar_demo_movimento.bat)
    pip install opencv-python numpy
    python deteccao_movimento_tempo_real.py

Controles: ESC = sair
"""

import cv2
import numpy as np

# ----------------------------------------------------------------------------
# Ajustes — CALIBRE na sala (luz/distância mudam os valores). Use o "motion=%"
# no rodapé: deixe-o perto de 0 parado e passando do LIMIAR quando você bate.
# ----------------------------------------------------------------------------
SENSIBILIDADE = 25.0   # ganho: maior = dispara mais fácil
LIMIAR        = 0.6    # acima disso -> "violência"
SUAVIZACAO    = 0.5
CAMERA        = 0


def main():
    cap = cv2.VideoCapture(CAMERA)
    if not cap.isOpened():
        raise SystemExit("Não consegui abrir a webcam. Tente trocar CAMERA=1.")

    anterior = None   # quadro anterior (em cinza/borrado)
    score = 0.0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)   # espelha (fica natural, tipo espelho)

        # prepara o quadro: cinza + leve desfoque pra ignorar ruído da câmera
        cinza = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cinza = cv2.GaussianBlur(cinza, (21, 21), 0)

        movimento = 0.0
        mask = None
        if anterior is not None:
            # diferença entre o quadro atual e o anterior
            diff = cv2.absdiff(anterior, cinza)
            _, mask = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
            # quanto da tela mudou (fração de pixels) = intensidade do movimento
            movimento = float(np.count_nonzero(mask)) / mask.size
        anterior = cinza

        # converte movimento em score 0..1 e suaviza pra não piscar
        bruto = min(1.0, movimento * SENSIBILIDADE)
        score = SUAVIZACAO * score + (1 - SUAVIZACAO) * bruto
        violencia = score >= LIMIAR

        # pinta de vermelho as regiões que se moveram (fica visual na demo)
        if mask is not None:
            overlay = np.zeros_like(frame)
            overlay[:, :, 2] = mask
            frame = cv2.addWeighted(frame, 1.0, overlay, 0.4, 0)

        cor = (0, 0, 255) if violencia else (0, 180, 0)
        rotulo = "VIOLENCIA DETECTADA" if violencia else "normal"
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 60), cor, -1)
        cv2.putText(frame, f"{rotulo}  {score*100:5.1f}%", (15, 42),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 2)
        cv2.putText(frame, f"motion={movimento*100:.2f}% da tela", (15, frame.shape[0]-15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        cv2.imshow("Deteccao por movimento (OpenCV) - ESC sai", frame)
        if cv2.waitKey(1) & 0xFF == 27:
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
