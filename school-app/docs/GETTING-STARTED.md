# Getting Athar running

Athar needs two things: the app, and a model for the Agent page. Everything except the Agent page works with no model at all, so you can look around first and add a model later.

All the data inside is made up. Do not put real learner data in it yet.

## Step 1: get the app

Pick one.

### A. Windows, no installing (easiest)

1. Download `Athar-windows-with-model.zip` (6.4 GB) from the [Athar folder on Google Drive](https://drive.google.com/drive/folders/1Fg7QVpYEbY4f-Tua_oJ7YMvfS3-1tjMO). The model is inside, so there is nothing else to download. Google cannot scan a file this large, so press **Download anyway**. For a small download, take `Athar-windows.zip` from the Releases page of this repository instead; the first start then offers to fetch the model.
2. Right-click the zip, choose **Extract All**, and open the extracted folder. Do not run it from inside the zip.
3. Double-click **Start Athar**. A black window opens and stays open. If Windows shows "Windows protected your PC", choose **More info**, then **Run anyway**.
4. Your browser opens at http://127.0.0.1:8780. If it does not, type that address yourself.

To stop, close the black window. To remove Athar, delete the folder. Nothing else on the computer is changed.

### B. From the source (Windows, Mac or Linux)

You need [uv](https://docs.astral.sh/uv/). Then:

```
git clone https://github.com/OmarAxis/Athar.git
cd Athar
uv sync
uv run athar demo
```

Open http://127.0.0.1:8765. The first run builds the made-up school.

The first time it opens, Athar asks who is using it: **a parent** or **a school**. It is the same program. Pick the one that fits; you can switch later in the settings.

## Step 2: give it a model

Pick one. You can change your mind later.

### 1. LM Studio on your computer (free, nothing leaves the computer)

1. Install [LM Studio](https://lmstudio.ai) and download a model in it. Athar is tested with **Qwen3.5 9B**. A computer with 16 GB of memory runs it.
2. In LM Studio, open the **Developer** tab and switch the server on. It listens at `http://localhost:1234`.
3. Start Athar. It finds LM Studio by itself. The black window says which model it will use, and the Agent page shows the same list of models so you can pick another.

Ollama works the same way: run `ollama serve` and Athar finds it at `http://localhost:11434`.

If you run Athar from the source and your model program is at a different address, set it before starting:

```
ATHAR_LLM_BASE_URL=http://localhost:1234/v1
ATHAR_LLM_MODEL=the-model-name-as-the-program-lists-it
```

### 2. Your own key for a model on the internet (OpenAI or Claude)

1. Open the **Agent** page (المساعد الآلي).
2. Open **Cloud models (optional): OpenAI and Claude**.
3. Paste your key, press **Use this key**, and choose a model.

The key is kept in memory only. It is not written to any file and it is forgotten when Athar stops. **Forget key** removes it sooner.

A model on the internet receives the document and the records the agent reads, by record code and without names. Use it with the made-up data only.

To have a key remembered between starts, or to use another provider such as OpenRouter or Groq:

- In the Windows package: open `settings.txt` in the Athar folder and follow the notes in it.
- From the source: set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`, or the three `ATHAR_LLM_...` settings listed in `.env.example`, in the shell that starts Athar. Hosted providers also need `ATHAR_LLM_REASONING=default`.

A key in `settings.txt` or in your shell is plain text on your own computer. Never put a key in a file inside this repository.

### 3. The model inside the Windows package

This is the way for someone who has never heard of LM Studio. The first time you start the Windows package with no model, the black window asks whether to download one. Press Enter and wait: it fetches two files, 6.1 GB in all, and then works with no internet. If you said no, do it later:

In the Athar folder, double-click **Download the model** once, with internet. It fetches two files, 6.1 GB in all, into the `models` folder and checks it. After that Athar runs its own model with no internet and no other program.

## Step 3: look around

**If you chose parent:** add your child, then add a result: take a photo of the marked paper and check the lines Athar fills in, or type them (the topic, the mark, and what it was out of). The home page shows what is going well and where to help first once there are about six marks. To see it full first, choose "Show a made-up child".

**If you chose school:**

- The page opens in Arabic. The button at the bottom of the side panel switches to English.
- Choose a teacher's name in the side panel. With made-up data there is no password.
- **في انتظار المراجعة** (Review queue) has findings waiting for a decision. From the source, run `uv run athar story` first to fill it without a model.
- **المساعد الآلي** (Agent): pick a learner, pick the quiz sheet in the list, and start a run. It reads the sheet, records the marks, and stops for a teacher.
- **إضافة سجلات** (Add records): download a marks sheet for Excel, fill it in, upload it.
- **المدرسة** (School): create the school admin to turn on sign-in, then add teachers and give them classes.

## If something goes wrong

- **The Agent page says the model did not answer.** Check that LM Studio's server is switched on and a model is loaded, or add a cloud key. Then reload the page.
- **The address does not open.** Something else may be using the port. The black window prints the address it chose.
- **A run is slow.** On a computer with no graphics card one run can take several minutes. A cloud model is the faster choice there.
- **To start again with a fresh school.** Windows package: stop Athar and delete its `data` folder. Source: `uv run athar seed`.

What is and is not finished is listed in the [README](../README.md). What the code protects, and what it does not, is in [SECURITY.md](../SECURITY.md).
