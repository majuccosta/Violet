# Detecção de Violência em Tempo Real

Protótipo de IA que **detecta violência física acontecendo ao vivo em uma câmera**.
O sistema combina duas peças que se complementam:

1. **Um classificador treinado** (transfer learning) que aprendeu, a partir de
   ~10 mil imagens, a distinguir cenas de **violência** de cenas **normais** — é
   daqui que sai a **acurácia** do modelo.
2. **Um detector em tempo real** que roda esse modelo (no formato leve **TFLite**)
   quadro a quadro na webcam, exibindo na tela se há violência acontecendo agora
   e com qual confiança.

> Disciplina de Inteligência Artificial — protótipo funcional + apresentação prática.

---

## 1. Intuição — o "porquê"

**Por que não treinamos a rede do zero?** Ensinar um computador a enxergar
(bordas, texturas, formas) exigiria milhões de imagens e muito tempo. Em vez
disso usamos **Transfer Learning**: partimos da **MobileNetV2**, uma rede que já
aprendeu a enxergar treinando em milhões de fotos (ImageNet). Nós **congelamos**
esse conhecimento e treinamos apenas uma pequena "cabeça" por cima, que aprende
só a decisão nova: *isto é violência ou não?*

**Classificação x Detecção — a sinceridade técnica.** O dataset rotula cada
imagem inteira como "violência/não" — ele **não** marca *onde* na imagem está a
agressão (não tem caixas delimitadoras). Logo, não dá pra treinar uma "detecção"
no sentido de YOLO. O que fazemos — e que na prática responde "tem violência
acontecendo agora?" — é rodar o **classificador quadro a quadro** sobre o vídeo
ao vivo. Funcionalmente, **classificação contínua sobre o tempo = detecção em
tempo real**. O **TFLite** é justamente o formato enxuto que torna essa
inferência rápida o suficiente pra rodar ao vivo.

**E o lado temporal?** Violência de verdade está no *movimento* (brusquidão e
intensidade), não num quadro isolado. Por isso o projeto traz também um
**detector de movimento** (só OpenCV), que mede o quanto a imagem muda de um
quadro pro outro — capturando a intuição "violência = movimento súbito e
intenso". Ver *Limitações*.

---

## 2. Código — as partes que importam

| Arquivo | O que faz |
|---|---|
| `treinar.py` | Treina o classificador (transfer learning) e **exporta o `.tflite`**. Roda em CPU. |
| `testar_modelo.py` | Testa o `.tflite` em imagens reais do dataset (sem webcam) — confirma que o modelo funciona. |
| `deteccao_tflite_tempo_real.py` | **A demo principal:** roda o modelo treinado ao vivo na webcam, com veredito estável. |
| `deteccao_movimento_tempo_real.py` | Detector de movimento (OpenCV) — captura a intuição temporal e é o plano B que sempre reage ao movimento. |
| `requirements.txt` / `requirements-treino.txt` | Dependências da demo / do treino. |

**Truque pra treinar em CPU com pouca RAM:** como a base MobileNetV2 está
congelada, o que ela "vê" em cada imagem nunca muda. Então passamos cada imagem
por ela **uma única vez**, guardamos o vetor de características e treinamos a
cabeça em cima desses vetores — segundos em vez de horas. O modelo final
exportado continua sendo a CNN completa.

```
imagem (160x160) ─▶ normaliza ─▶ MobileNetV2 (congelada) ─▶ cabeça (Dense) ─▶ P(violência)
```

---

## 3. Funcionamento — como rodar

### a) Treinar o modelo (gera o `.tflite`)
```bash
pip install -r requirements-treino.txt
python treinar.py
```
Baixa o dataset, treina, e gera: `modelo_violencia.keras`, **`modelo_violencia.tflite`**,
`matriz_confusao.png`, `historico_treino.png` e `metricas.txt`.

### b) Demo ao vivo na webcam
```bash
pip install -r requirements.txt
python deteccao_tflite_tempo_real.py        # modelo treinado rodando ao vivo
python deteccao_movimento_tempo_real.py     # plano B: sempre reage ao movimento
```
No **Windows**, dá pra simplesmente dar **dois cliques** em `rodar_demo_tflite.bat`.
Abre a janela da webcam com o rótulo (**VIOLÊNCIA DETECTADA / normal**), a
porcentagem de confiança e uma barra com a marca do limiar. `ESC` fecha.

### Resultados do modelo

> **Acurácia no conjunto de teste: 95,48%** — em 1.661 imagens nunca vistas no treino.

| Classe | Precisão | Recall | F1 |
|---|---|---|---|
| não-violência | 96,7% | 93,6% | 95,1% |
| violência | 94,5% | 97,2% | 95,8% |

A matriz de confusão (`matriz_confusao.png`): de 877 cenas de violência o modelo
acertou 852 (errou 25); de 784 cenas normais acertou 734 (50 falsos positivos).
O desempenho **equilibrado entre as duas classes** mostra que o modelo de fato
separou violência de não-violência — diferente de uma acurácia inflada por
desbalanceamento.

---

## 4. Limitações (e honestidade sobre elas)

- **Confiança ≠ Acurácia.** A porcentagem que aparece na webcam é a *confiança do
  modelo naquele instante*. A **acurácia** é a taxa de acerto medida no conjunto
  de teste, durante o treino — são coisas diferentes.
- **Diferença de domínio + viés de dataset (visto na prática).** O modelo
  aprendeu com imagens de filmes/CCTV, onde cenas de violência costumam ser
  *dinâmicas, borradas e a distância*. Testando na webcam, ele às vezes acusou
  "violência" quando as pessoas estavam **longe** ou **saindo do quadro** — porque
  aprendeu o atalho "cena agitada/atípica = violência", não a violência em si.
  É viés de dataset acontecendo ao vivo. Por isso o detector de movimento existe
  como rede de segurança, e o ideal seria treinar com dados do próprio ambiente.
- **Um quadro perde o movimento.** Classificar imagem a imagem ignora a dimensão
  temporal, que é onde a violência realmente se manifesta. A evolução natural do
  projeto seria um modelo de vídeo (CNN+LSTM ou 3D).
- **Não existe dataset de violência em *sala de aula*.** Os datasets públicos são
  de briga de rua / CFTV / filme; nenhum casa com o cenário específico de uma
  câmera de sala. Isso limita a precisão no caso de uso real.
- **Ética.** Vigilância automatizada levanta questões de privacidade e de
  falsos positivos (esporte, brincadeira) que penalizariam pessoas injustamente.

---

## Dataset

[Real Life Violence Situations](https://www.kaggle.com/datasets/abdulmananraja/real-life-violence-situations)
(Kaggle) — ~10 mil imagens em duas classes (`violence` / `non_violence`).
Não versionado no Git (grande e reprodutível pelo `treinar.py`).
