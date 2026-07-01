"""
treinar.py — Treinamento do detector de violência (transfer learning)
=====================================================================

INTUIÇÃO (o "porquê", pra defender na apresentação)
---------------------------------------------------
Não dá pra ensinar uma rede a "enxergar" do zero em uma noite — isso levaria
milhões de imagens e muito tempo. Então usamos TRANSFER LEARNING:

  1. Pegamos a MobileNetV2, uma rede que JÁ aprendeu a enxergar bordas,
     texturas e formas treinando em milhões de fotos (ImageNet).
  2. CONGELAMOS essa base (não mexemos no que ela já sabe).
  3. Treinamos só uma "cabeça" pequena por cima, que aprende a tarefa nova:
     dado o que a base extraiu, isto é violência ou não?

TRUQUE PRA RODAR EM CPU COM POUCA RAM
-------------------------------------
Passar 10 mil imagens pela MobileNetV2 a cada época seria lento. Como a base
está congelada, o que ela "vê" em cada imagem NUNCA muda. Então passamos cada
imagem pela base UMA ÚNICA VEZ, guardamos o vetor de características (1280
números) e treinamos a cabeça em cima desses vetores. Isso transforma horas
de treino em segundos, e o modelo final exportado continua sendo a CNN inteira.

SAÍDAS GERADAS
--------------
  modelo_violencia.keras   -> modelo completo (imagem -> P(violência))
  modelo_violencia.tflite  -> mesmo modelo, leve, pra rodar ao vivo na webcam
  matriz_confusao.png      -> onde o modelo acerta/erra (pra apresentação)
  historico_treino.png     -> curva de acurácia ao longo do treino
  metricas.txt             -> acurácia real no conjunto de teste + relatório
"""

import os
import sys
import numpy as np

# ----------------------------------------------------------------------------
# Configuração
# ----------------------------------------------------------------------------
IMG_SIZE = 160          # MobileNetV2 aceita 160x160; menor = mais rápido em CPU
BATCH    = 32
SEED     = 42
EPOCHS   = 30           # treino da cabeça é rápido; EarlyStopping corta antes
AQUI     = os.path.dirname(os.path.abspath(__file__))
CACHE    = os.path.join(AQUI, "features_cache.npz")
EXTS     = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

np.random.seed(SEED)


def log(msg):
    print(f"\n>>> {msg}", flush=True)


# ----------------------------------------------------------------------------
# 1. Garantir o dataset (baixa do Kaggle se DATA_DIR não for informado)
# ----------------------------------------------------------------------------
def garantir_dataset():
    d = os.environ.get("DATA_DIR", "").strip()
    if d and os.path.isdir(d):
        log(f"Usando dataset informado em DATA_DIR: {d}")
        return d
    log("Baixando dataset do Kaggle (pode levar alguns minutos)...")
    import kagglehub
    p = kagglehub.dataset_download("abdulmananraja/real-life-violence-situations")
    log(f"Dataset baixado em: {p}")
    return p


# ----------------------------------------------------------------------------
# 2. Descobrir as duas classes (violence / non_violence) de forma robusta
#    — não importa quantos níveis de subpasta o dataset tenha.
# ----------------------------------------------------------------------------
def encontrar_arquivos(raiz):
    # mapeia: cada pasta que contém imagens -> lista de caminhos
    pastas = {}
    for dirpath, _, filenames in os.walk(raiz):
        imgs = [os.path.join(dirpath, f) for f in filenames
                if f.lower().endswith(EXTS)]
        if imgs:
            pastas[dirpath] = imgs

    # classifica cada pasta pelo nome: "non" -> não-violência, senão "viol" -> violência
    arquivos, rotulos = [], []
    achou = {"violence": 0, "non_violence": 0}
    for pasta, imgs in pastas.items():
        nome = os.path.basename(pasta).lower()
        if "non" in nome or "no_" in nome or nome.startswith("normal"):
            rot = 0  # non_violence
            achou["non_violence"] += len(imgs)
        elif "viol" in nome or "fight" in nome or "assault" in nome:
            rot = 1  # violence
            achou["violence"] += len(imgs)
        else:
            continue  # pasta que não é de classe (ex.: raiz, metadados)
        arquivos.extend(imgs)
        rotulos.extend([rot] * len(imgs))

    log("Pastas com imagens encontradas:")
    for pasta, imgs in sorted(pastas.items()):
        print(f"    {len(imgs):6d}  {pasta}")
    log(f"Total rotulado -> violência: {achou['violence']} | "
        f"não-violência: {achou['non_violence']}")

    if achou["violence"] == 0 or achou["non_violence"] == 0:
        print("\nERRO: não consegui identificar as DUAS classes pelo nome das "
              "pastas. Veja a lista acima e me diga a estrutura.", file=sys.stderr)
        sys.exit(1)

    return np.array(arquivos), np.array(rotulos, dtype=np.float32)


# ----------------------------------------------------------------------------
# 3. Extrair características (passa cada imagem pela MobileNetV2 UMA vez)
# ----------------------------------------------------------------------------
def construir_extrator(keras, layers):
    """Modelo: imagem(0..255) -> normaliza -> MobileNetV2 congelada -> vetor 1280."""
    base = keras.applications.MobileNetV2(
        include_top=False, weights="imagenet",
        input_shape=(IMG_SIZE, IMG_SIZE, 3), pooling="avg")
    base.trainable = False  # CONGELA: preserva o que ela já aprendeu

    entrada = keras.Input((IMG_SIZE, IMG_SIZE, 3))            # pixels 0..255
    x = layers.Rescaling(1.0 / 127.5, offset=-1.0)(entrada)  # -> faixa [-1, 1]
    x = base(x, training=False)
    return keras.Model(entrada, x, name="extrator_features")


def extrair_features(tf, keras, layers, arquivos, rotulos):
    if os.path.exists(CACHE) and not os.environ.get("FORCE_RECOMPUTE"):
        log("Carregando features do cache (features_cache.npz)...")
        d = np.load(CACHE)
        return d["feats"], d["labs"]

    from PIL import Image
    AUTOTUNE = tf.data.AUTOTUNE

    def carregar(path_bytes):
        # carrega com PIL e ignora arquivos corrompidos (retorna flag ok)
        try:
            img = (Image.open(path_bytes.decode("utf-8"))
                   .convert("RGB").resize((IMG_SIZE, IMG_SIZE)))
            return np.asarray(img, dtype=np.float32), np.bool_(True)
        except Exception:
            return np.zeros((IMG_SIZE, IMG_SIZE, 3), np.float32), np.bool_(False)

    ds = tf.data.Dataset.from_tensor_slices((arquivos, rotulos))

    def _map(path, label):
        img, ok = tf.numpy_function(carregar, [path], [tf.float32, tf.bool])
        img.set_shape((IMG_SIZE, IMG_SIZE, 3))
        ok.set_shape(())
        return img, label, ok

    ds = (ds.map(_map, num_parallel_calls=AUTOTUNE)
            .filter(lambda img, lbl, ok: ok)          # descarta corrompidas
            .map(lambda img, lbl, ok: (img, lbl))
            .batch(BATCH).prefetch(AUTOTUNE))

    extrator = construir_extrator(keras, layers)
    log("Extraindo características (passada única pela MobileNetV2)...")
    feats, labs = [], []
    total = 0
    for img_b, lab_b in ds:
        feats.append(extrator(img_b, training=False).numpy())
        labs.append(lab_b.numpy())
        total += len(lab_b)
        print(f"\r    {total} imagens processadas", end="", flush=True)
    print()
    feats = np.concatenate(feats)
    labs = np.concatenate(labs)
    descartadas = len(arquivos) - len(labs)
    log(f"Features: {feats.shape} | imagens descartadas (corrompidas): {descartadas}")
    np.savez(CACHE, feats=feats, labs=labs)
    return feats, labs


# ----------------------------------------------------------------------------
# 4. Treinar a cabeça, avaliar, salvar modelo e exportar TFLite
# ----------------------------------------------------------------------------
def main():
    log("Importando TensorFlow (demora um pouco na 1ª vez)...")
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import (accuracy_score, confusion_matrix,
                                  classification_report)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tf.random.set_seed(SEED)

    raiz = garantir_dataset()
    arquivos, rotulos = encontrar_arquivos(raiz)
    feats, labs = extrair_features(tf, keras, layers, arquivos, rotulos)

    # split estratificado 70% treino / 15% validação / 15% teste
    Xtr, Xtmp, ytr, ytmp = train_test_split(
        feats, labs, test_size=0.30, stratify=labs, random_state=SEED)
    Xval, Xte, yval, yte = train_test_split(
        Xtmp, ytmp, test_size=0.50, stratify=ytmp, random_state=SEED)
    log(f"Treino: {len(ytr)} | Validação: {len(yval)} | Teste: {len(yte)}")

    # a "cabeça": uma rede pequena que decide violência a partir das features
    cabeca = keras.Sequential([
        keras.Input((feats.shape[1],)),
        layers.Dense(64, activation="relu"),
        layers.Dropout(0.3),                 # evita decorar (overfitting)
        layers.Dense(1, activation="sigmoid")  # saída = P(violência) entre 0 e 1
    ], name="cabeca_classificadora")
    cabeca.compile(optimizer="adam", loss="binary_crossentropy",
                   metrics=["accuracy"])

    log("Treinando a cabeça...")
    parada = keras.callbacks.EarlyStopping(
        patience=6, restore_best_weights=True, monitor="val_accuracy")
    hist = cabeca.fit(Xtr, ytr, validation_data=(Xval, yval),
                      epochs=EPOCHS, batch_size=64, callbacks=[parada], verbose=2)

    # ---- avaliação no conjunto de TESTE (a acurácia "de verdade") ----
    proba = cabeca.predict(Xte, verbose=0).ravel()
    pred = (proba >= 0.5).astype(int)
    acc = accuracy_score(yte, pred)
    cm = confusion_matrix(yte, pred)
    nomes = ["non_violence", "violence"]
    report = classification_report(yte, pred, target_names=nomes, digits=4)

    log(f"ACURÁCIA NO TESTE: {acc*100:.2f}%")
    print(report)
    print("Matriz de confusão (linhas=real, colunas=previsto):")
    print(cm)

    with open(os.path.join(AQUI, "metricas.txt"), "w") as f:
        f.write(f"Acuracia no teste: {acc*100:.2f}%\n\n")
        f.write(report + "\n")
        f.write("Matriz de confusao (linhas=real, colunas=previsto):\n")
        f.write(str(cm) + "\n")

    # ---- gráficos pra apresentação ----
    plt.figure()
    plt.plot(hist.history["accuracy"], label="treino")
    plt.plot(hist.history["val_accuracy"], label="validação")
    plt.xlabel("época"); plt.ylabel("acurácia"); plt.legend()
    plt.title("Aprendizado da cabeça classificadora")
    plt.savefig(os.path.join(AQUI, "historico_treino.png"), dpi=120, bbox_inches="tight")

    plt.figure()
    plt.imshow(cm, cmap="Blues")
    plt.xticks([0, 1], nomes); plt.yticks([0, 1], nomes)
    plt.xlabel("previsto"); plt.ylabel("real"); plt.title(f"Matriz de confusão (acc {acc*100:.1f}%)")
    for i in range(2):
        for j in range(2):
            plt.text(j, i, cm[i, j], ha="center", va="center",
                     color="white" if cm[i, j] > cm.max()/2 else "black")
    plt.colorbar()
    plt.savefig(os.path.join(AQUI, "matriz_confusao.png"), dpi=120, bbox_inches="tight")

    # ---- montar o modelo COMPLETO (imagem -> P(violência)) e salvar ----
    log("Montando e salvando o modelo completo...")
    extrator = construir_extrator(keras, layers)
    saida = cabeca(extrator.output)
    modelo = keras.Model(extrator.input, saida, name="detector_violencia")
    modelo.save(os.path.join(AQUI, "modelo_violencia.keras"))

    # ---- exportar TFLite (formato leve pra rodar ao vivo na webcam) ----
    log("Exportando para TFLite...")
    sm_dir = os.path.join(AQUI, "_saved_model_tmp")
    modelo.export(sm_dir)  # Keras 3 -> SavedModel (rota robusta de conversão)
    conv = tf.lite.TFLiteConverter.from_saved_model(sm_dir)
    conv.optimizations = [tf.lite.Optimize.DEFAULT]  # quantização -> menor e mais rápido
    tflite = conv.convert()
    tflite_path = os.path.join(AQUI, "modelo_violencia.tflite")
    with open(tflite_path, "wb") as f:
        f.write(tflite)
    log(f"TFLite salvo: {tflite_path} ({len(tflite)/1e6:.2f} MB)")

    # ---- conferência: o TFLite dá o mesmo resultado do Keras? ----
    interp = tf.lite.Interpreter(model_path=tflite_path)
    interp.allocate_tensors()
    inp = interp.get_input_details()[0]
    out = interp.get_output_details()[0]
    amostra = np.zeros((1, IMG_SIZE, IMG_SIZE, 3), dtype=np.float32)
    interp.set_tensor(inp["index"], amostra)
    interp.invoke()
    log(f"Sanidade TFLite OK — formato de entrada {inp['shape']}, "
        f"saída exemplo {float(interp.get_tensor(out['index'])[0][0]):.3f}")

    log("CONCLUÍDO. Arquivos prontos: modelo_violencia.keras / .tflite, "
        "matriz_confusao.png, historico_treino.png, metricas.txt")


if __name__ == "__main__":
    main()
