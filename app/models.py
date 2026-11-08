import json
import re
import threading
import time
import httpx
from app.security import SYSTEM
from app.quotas import reserve_model_call

BASELINE_SYSTEM = ("Answer the question from evidence with [chunk_id] citations. "
                   "If evidence is absent say 'Insufficient evidence.'")


class ProviderError(RuntimeError):
    pass


class Model:
    def __init__(self, settings):
        self.settings = settings
        self.semaphore = threading.BoundedSemaphore(2)
        if settings.provider != "extractive" and settings.model == "extractive-v1":
            raise ValueError("Configure a model ID for the selected provider")
        if settings.provider == "gemini" and not settings.gemini_api_key:
            raise ValueError("Gemini API key is required")
        if settings.provider == "gemini" and not re.fullmatch(r"[A-Za-z0-9._-]+", settings.model):
            raise ValueError("Invalid Gemini model identifier")

    def generate(self, question, chunks, mode):
        # Offline mode is grounded extraction, never a simulated vulnerable LLM.
        if self.settings.provider == "extractive":
            if not chunks:
                return {"text": "Insufficient evidence.", "input_tokens": None, "output_tokens": None}
            question_words = set(re.findall(r"\w+", question.lower()))
            candidates = []
            for chunk in chunks:
                for sentence in re.split(r"(?<=[.!?])\s+|\n", chunk["text"]):
                    if sentence.strip():
                        score = len(question_words & set(re.findall(r"\w+", sentence.lower())))
                        candidates.append((score, sentence.strip(), chunk["id"]))
            best = sorted(candidates, key=lambda item: -item[0])[:2]
            text = "\n".join(f"{sentence} [{cid}]" for _, sentence, cid in best)
            return {"text": text[:self.settings.max_output_tokens * 3],
                    "input_tokens": None, "output_tokens": None}
        policy = SYSTEM if mode == "protected" else BASELINE_SYSTEM
        prompt = json.dumps({"question": question, "evidence": [
            {"chunk_id": c["id"], "text": c["text"]} for c in chunks]}, ensure_ascii=False)
        with self.semaphore, httpx.Client(timeout=self.settings.timeout) as client:
            for attempt in range(self.settings.retries + 1):
                if hasattr(self, "budget_store"):
                    reserve_model_call(self.budget_store, self.settings)
                try:
                    if self.settings.provider == "gemini":
                        response = client.post(
                            f"https://generativelanguage.googleapis.com/v1beta/models/{self.settings.model}:generateContent",
                            headers={"x-goog-api-key": self.settings.gemini_api_key},
                            json={"systemInstruction": {"parts": [{"text": policy}]},
                                  "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                                  "generationConfig": {"maxOutputTokens": self.settings.max_output_tokens,
                                                       "temperature": 0}})
                    else:
                        response = client.post(self.settings.ollama_url.rstrip("/") + "/api/chat",
                            json={"model": self.settings.model, "stream": False,
                                  "messages": [{"role": "system", "content": policy},
                                               {"role": "user", "content": prompt}],
                                  "options": {"num_predict": self.settings.max_output_tokens,
                                              "temperature": 0}})
                    if response.status_code in (429, 500, 502, 503, 504) and attempt < self.settings.retries:
                        time.sleep(0.25 * (attempt + 1))
                        continue
                    response.raise_for_status()
                    data = response.json()
                    if self.settings.provider == "gemini":
                        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                        usage = data.get("usageMetadata", {})
                        result = {"text": text, "input_tokens": usage.get("promptTokenCount"),
                                  "output_tokens": usage.get("candidatesTokenCount")}
                    else:
                        result = {"text": data["message"]["content"],
                                  "input_tokens": data.get("prompt_eval_count"),
                                  "output_tokens": data.get("eval_count")}
                    if not result["text"]:
                        raise ProviderError("Provider returned no answer")
                    version = data.get("modelVersion") if self.settings.provider == "gemini" else data.get("model")
                    if version:
                        result["model_version"] = version
                    return result
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    if attempt < self.settings.retries:
                        continue
                    raise ProviderError("Provider unavailable or timed out") from exc
                except (httpx.HTTPStatusError, ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
                    raise ProviderError("Provider returned an invalid or unsuccessful response") from exc
        raise ProviderError("Provider request failed")
