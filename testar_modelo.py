"""
testar_modelo.py — testa o modelo .tflite em IMAGENS REAIS (sem precisar de webcam)
==================================================================================
Pega algumas imagens de cada classe do dataset, roda o modelo treinado e mostra
o que ele previu. Serve pra confirmar que o .tflite funciona ANTES de levar pra
demo ao vivo. É a mesma inferência que roda na webcam, só que em fotos paradas.

    python testar_modelo.py
"""

import os
import random
import numpy as np
from PIL import Image

IMG = 160
MODELO = "modelo_violencia.tflite"
N_POR_CLASSE = 12
random.seed(1)


def carregar_interpreter(caminho):
    for origem in ("tflite_runtime.interpreter", "ai_edge_litert.interpreter"):
        try:
            mod = __import__(origem, fromlist=["Interpreter"])
            return mod.Interpreter
        except Exception:
            pass
    import tensorflow as tf            # fallback: interpreter embutido no TensorFlow
    return tf.lite.Interpreter


def achar_pastas(raiz):
    violence = nonviolence = None
    exts = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
    for d, _, fs in os.walk(raiz):
        if not any(f.lower().endswith(exts) for f in fs):
            continue
        nome = os.path.basename(d).lower()
        if "non" in nome:
            nonviolence = d
        elif "viol" in nome:
            violence = d
    return violence, nonviolence


def main():
    # localiza o dataset (já em cache do treino; download é instantâneo)
    import kagglehub
    raiz = kagglehub.dataset_download("abdulmananraja/real-life-violence-situations")
    pasta_v, pasta_nv = achar_pastas(raiz)
    print(f"violence:     {pasta_v}")
    print(f"non_violence: {pasta_nv}\n")

    Interpreter = carregar_interpreter(MODELO)
    interp = Interpreter(model_path=MODELO)
    interp.allocate_tensors()
    ent = interp.get_input_details()[0]
    sai = interp.get_output_details()[0]

    def prever(caminho):
        img = Image.open(caminho).convert("RGB").resize((IMG, IMG))
        x = np.expand_dims(np.asarray(img, np.float32), 0)
        interp.set_tensor(ent["index"], x)
        interp.invoke()
        return float(interp.get_tensor(sai["index"]).ravel()[0])  # P(violência)

    exts = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
    amostras = []
    for pasta, rotulo in [(pasta_v, 1), (pasta_nv, 0)]:
        arqs = [os.path.join(pasta, f) for f in os.listdir(pasta)
                if f.lower().endswith(exts)]
        for a in random.sample(arqs, min(N_POR_CLASSE, len(arqs))):
            amostras.append((a, rotulo))

    print(f"{'real':<14}{'P(viol)':>9}   {'previu':<14}{'ok?'}")
    print("-" * 48)
    acertos = 0
    for caminho, real in amostras:
        p = prever(caminho)
        previu = 1 if p >= 0.5 else 0
        ok = (previu == real)
        acertos += ok
        print(f"{'violência' if real else 'normal':<14}{p*100:7.1f}%   "
              f"{'violência' if previu else 'normal':<14}{'✓' if ok else '✗ ERRO'}")

    print("-" * 48)
    print(f"Acertos na amostra: {acertos}/{len(amostras)} "
          f"({100*acertos/len(amostras):.1f}%)")


if __name__ == "__main__":
    main()
