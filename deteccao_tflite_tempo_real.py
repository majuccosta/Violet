"""
deteccao_tflite_tempo_real.py
=============================
Roda o modelo TREINADO (.tflite) AO VIVO na webcam, quadro a quadro.
É a "detecção em tempo real" que o professor pediu: o classificador rodando
continuamente sobre o vídeo da câmera = detector de "tem violência agora?".

>>> RODE NO WINDOWS <<<  (ou dê 2 cliques em rodar_demo_tflite.bat)
    pip install opencv-python numpy ai-edge-litert
    python deteccao_tflite_tempo_real.py

Controles:  ESC = sair

ESTABILIDADE DO VEREDITO
------------------------
Rodar quadro a quadro faz a probabilidade tremer (um soco borra a imagem). Pra
o sistema CRAVAR uma decisão em vez de piscar, usamos duas camadas:
  1. SUAVIZAÇÃO: média móvel que tira o tremor quadro-a-quadro.
  2. HOLD: ao ver um sinal forte de violência, trava o veredito por HOLD_SEG
     segundos. Assim, mesmo que alguns quadros oscilem, ele segura "VIOLÊNCIA
     DETECTADA" enquanto a agressão está acontecendo.

A porcentagem é a CONFIANÇA do modelo no momento — não a "acurácia" (essa é a
métrica medida no conjunto de teste, durante o treino: ~95%).
"""

import os
import time
import cv2
import numpy as np

# ----------------------------------------------------------------------------
# Ajustes (calibre na sala se precisar)
# ----------------------------------------------------------------------------
MODELO     = "modelo_violencia.tflite"
SUAVIZACAO = 0.5     # 0 = sem suavizar; mais alto = mais suave/estável
LIMIAR     = 0.55    # score acima disso conta como "sinal forte de violência"
HOLD_SEG   = 1.5     # segura o veredito "violência" por X s após o último sinal forte
CAMERA     = 0       # índice da webcam (troque pra 1 se tiver outra)


def carregar_interpreter(caminho):
    """Usa o runtime leve LiteRT (ai-edge-litert); cai pro TensorFlow se preciso."""
    Interpreter = None
    for origem in ("ai_edge_litert.interpreter", "tflite_runtime.interpreter"):
        try:
            mod = __import__(origem, fromlist=["Interpreter"])
            Interpreter = mod.Interpreter
            break
        except Exception:
            continue
    if Interpreter is None:
        import tensorflow as tf       # fallback: interpreter embutido no tensorflow
        Interpreter = tf.lite.Interpreter
    interp = Interpreter(model_path=caminho)
    interp.allocate_tensors()
    return interp


def main():
    if not os.path.exists(MODELO):
        raise SystemExit(f"Não achei '{MODELO}'. Coloque o .tflite nesta pasta.")

    interp = carregar_interpreter(MODELO)
    ent = interp.get_input_details()[0]
    sai = interp.get_output_details()[0]
    _, H, W, _ = ent["shape"]            # tamanho que o modelo espera (160x160)
    dtype = ent["dtype"]

    cap = cv2.VideoCapture(CAMERA)
    if not cap.isOpened():
        raise SystemExit("Não consegui abrir a webcam. Tente trocar CAMERA=1.")

    score = 0.0
    ultimo_forte = -999.0   # instante (s) do último sinal forte de violência
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        # ---- pré-processa o quadro do jeito que o modelo foi treinado ----
        img = cv2.resize(frame, (W, H))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)         # OpenCV é BGR; modelo é RGB
        entrada = np.expand_dims(img.astype(np.float32), 0)   # pixels 0..255
        if dtype == np.uint8:                              # se o modelo for quantizado int
            entrada = img[np.newaxis].astype(np.uint8)

        # ---- inferência: P(violência) deste quadro ----
        interp.set_tensor(ent["index"], entrada)
        interp.invoke()
        p = float(interp.get_tensor(sai["index"]).ravel()[0])

        # ---- camada de decisão: suaviza + segura o veredito ----
        score = SUAVIZACAO * score + (1 - SUAVIZACAO) * p
        agora = time.monotonic()
        if score >= LIMIAR:
            ultimo_forte = agora                 # registrou sinal forte agora
        violencia = (agora - ultimo_forte) <= HOLD_SEG   # segura por HOLD_SEG s

        # ---- desenha o resultado ----
        h, w = frame.shape[:2]
        cor = (0, 0, 255) if violencia else (0, 180, 0)
        rotulo = "VIOLENCIA DETECTADA" if violencia else "normal"
        cv2.rectangle(frame, (0, 0), (w, 60), cor, -1)
        cv2.putText(frame, f"{rotulo}  {score*100:5.1f}%", (15, 42),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 2)

        # barra de confiança com a marca do limiar
        bx, by, bw, bh = 15, h - 40, w - 30, 22
        cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), (255, 255, 255), 1)
        cv2.rectangle(frame, (bx, by), (bx + int(bw * score), by + bh), cor, -1)
        lx = bx + int(bw * LIMIAR)
        cv2.line(frame, (lx, by - 4), (lx, by + bh + 4), (0, 255, 255), 2)

        cv2.imshow("Deteccao de violencia (TFLite) - ESC sai", frame)
        if cv2.waitKey(1) & 0xFF == 27:   # ESC
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
