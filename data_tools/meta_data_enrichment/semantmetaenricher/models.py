import abc
import asyncio
import functools
import json
import os
from typing import Annotated, Literal, Optional

import openai
from classconfig import ConfigurableMixin, CreatableMixin, ConfigurableValue
from jinja2 import Environment
from jinja2.exceptions import TemplateError
from openai import AsyncOpenAI
from pydantic import BaseModel, Field, create_model

# Global registry of multitask classification labels
TASK_CLASSES = {
    "communicative_mode": [
        "narration", "description", "exposition", "argumentation",
        "instruction", "record", "interaction", "expression", "rhetorics",
        "uncertain"
    ],
    "complexity": [
        "very_easy", "easy", "moderate", "advanced", "expert", "uncertain"
    ],
    "documentary_role": [
        "journalistic", "scholarly", "literary", "legal", "administrative",
        "religious", "educational", "commercial", "personal",
        "official_public_communication", "reference", "uncertain"
    ],
    "emotional_tone": [
        "neutral_or_detached", "solemn_or_grave", "celebratory_or_triumphant",
        "anxious_or_alarmed", "mournful_or_elegiac", "indignant_or_outraged",
        "hopeful_or_aspirational", "reverent_or_devotional", "ironic_or_sardonic",
        "affectionate_or_tender", "uncertain"
    ],
    "geographic_scope": [
        "hyper_local", "local_or_municipal", "regional", "national",
        "multi_national_or_continental", "global_or_universal", "non_geographic",
        "uncertain"
    ],
    "information_granularity": [
        "general_overview", "detailed_account", "highly_specific", "definitional",
        "enumerative", "uncertain"
    ],
    "intertextual_density": [
        "no_references", "sparse", "moderate", "dense", "uncertain"
    ],
    "named_entity_focus": [
        "person_centric", "organization_centric", "place_centric", "event_centric",
        "work_centric", "concept_or_topic_centric", "mixed", "uncertain"
    ],
    "narrative_perspective": [
        "first_person_singular", "first_person_plural", "second_person",
        "third_person_personal", "third_person_impersonal", "mixed_or_shifting",
        "uncertain"
    ],
    "quantitative_content_density": [
        "no_quantitative", "incidental_numbers", "moderate_quantitative", "data_rich",
        "uncertain"
    ],
    "reliability_signals": [
        "evidence_based", "source_attributed", "first_hand_account",
        "procedurally_documented", "analytical_inference", "speculative_or_uncertain",
        "asserted_without_support", "promotional_or_advocacy",
        "partisan_or_propagandistic", "fictional_or_imaginative_frame", "uncertain"
    ],
    "structural_form": [
        "continuous_prose", "verse_lines", "list_or_enumeration", "tabular",
        "form_based_record", "ledger_or_account_entry", "header_or_title_block",
        "dialogue_turns", "navigation_or_reference_apparatus", "quoted_block",
        "entry_like_units", "other_structure", "garbage", "uncertain"
    ],
    "style": [
        "formal", "neutral", "informal", "bureaucratic", "scholarly",
        "journalistic", "didactic", "devotional", "literary", "promotional",
        "formulaic", "uncertain"
    ],
    "subject_domain": [
        "ddc_000_generalia", "ddc_100_philosophy_psychology", "ddc_200_religion",
        "ddc_300_social_sciences", "ddc_400_language", "ddc_500_natural_sciences",
        "ddc_600_applied_sciences", "ddc_700_arts_recreation", "ddc_800_literature",
        "ddc_900_history_geography", "news_and_current_affairs",
        "official_and_legal_documents", "personal_and_private_documents",
        "commercial_and_trade_documents", "uncertain"
    ],
    "temporal_reference_frame": [
        "contemporary_to_authorship", "historical_past", "remote_or_mythological_past",
        "future_or_projective", "timeless_or_general", "mixed_temporal", "uncertain"
    ],
    "textual_stance": [
        "neutral_descriptive", "interpretive", "evaluative", "persuasive",
        "normative", "committed_assertive", "hedged_or_cautious",
        "partisan_or_polemical", "satirical_or_ironic", "uncertain"
    ]
}

# Directory bundled with the package containing the default Jinja2 prompt template for each task.
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


def default_task_prompt_paths() -> dict[str, str]:
    """Path to the bundled default Jinja2 prompt template file for every task in TASK_CLASSES."""
    return {task: os.path.join(PROMPTS_DIR, f"{task}.j2") for task in TASK_CLASSES}


@functools.lru_cache(maxsize=None)
def build_structured_output_model(task: str) -> type[BaseModel]:
    """Build a per-task structured output model whose `cls` field is restricted to that task's own labels.

    Using a `Literal` of TASK_CLASSES[task] instead of a general `str` lets the API's
    structured-output / JSON-schema enforcement reject any label outside the task's class list,
    rather than relying on the model to only ever produce a valid one.

    :param task: The task name for which to build the structured output model.
    :return: A Pydantic model class with a `cls` field restricted to the task's own labels.
    """
    label_type = Literal[tuple(TASK_CLASSES[task])]

    cls_field = (Annotated[list[label_type], Field(min_length=1, max_length=2)], ...)

    return create_model(f"StructuredOutput_{task}", cls=cls_field)


class Model(ConfigurableMixin, CreatableMixin, abc.ABC):
    """Base class for configurable models."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    @abc.abstractmethod
    def generate(self, database_record: dict[str, str], tasks: list[str]) -> dict[str, list[str]]:
        """Perform classification for the given tasks on the database record.
        
        Args:
            database_record: Dictionary of database record fields.
            tasks: List of task names to classify.
            
        Returns:
            Dictionary mapping each task name to its predicted class string.
        """
        pass

    def generate_batch(self, database_records: list[dict[str, str]], tasks: list[str]) -> list[dict[str, list[str]]]:
        """Perform classification for the given tasks on a batch of database records.
        
        Args:
            database_records: List of dictionaries of database record fields.
            tasks: List of task names to classify.
            
        Returns:
            List of dictionaries mapping each task name to its predicted class string.
        """
        return [self.generate(record, tasks) for record in database_records]


class APIModel(Model):
    """Model that connects to OpenAI-compatible APIs using structured outputs."""
    
    api_key: Optional[str] = ConfigurableValue(
        desc="API Key (optional, defaults to environment variable)",
        user_default=None,
        voluntary=True
    )
    base_url: str = ConfigurableValue(
        desc="Base URL for the OpenAI compatible API",
        user_default="https://api.openai.com/v1"
    )
    model_name: str = ConfigurableValue(
        desc="Model name to use (e.g. gpt-4o, local-model)",
        user_default="gpt-3.5-turbo"
    )
    temperature: float = ConfigurableValue(
        desc="Temperature for sampling",
        user_default=0.7
    )
    max_tokens: int = ConfigurableValue(
        desc="Maximum number of tokens to generate",
        user_default=150
    )
    task_prompts: dict[str, str] = ConfigurableValue(
        desc="Dictionary mapping task names to paths of Jinja2 prompt template files",
        user_default=default_task_prompt_paths()
    )
    concurrency_limit: int = ConfigurableValue(
        desc="Maximum number of concurrent API requests",
        user_default=5
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.jinja_env = Environment()
        self.task_templates = {}
        for task, prompt_path in self.task_prompts.items():
            with open(prompt_path, encoding="utf-8") as f:
                self.task_templates[task] = self.jinja_env.from_string(f.read())

    def __enter__(self):
        self._loop = asyncio.new_event_loop()
        self.client = AsyncOpenAI(
            api_key=self.api_key or os.environ.get("OPENAI_API_KEY") or "dummy-key",
            base_url=self.base_url
        )
        self.semaphore = asyncio.Semaphore(self.concurrency_limit)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self._loop.run_until_complete(self.client.close())
        finally:
            self._loop.close()
        return False

    def generate(self, database_record: dict[str, str], tasks: list[str]) -> dict[str, list[str]]:
        return self.generate_batch([database_record], tasks)[0]

    def generate_batch(self, database_records: list[dict[str, str]], tasks: list[str]) -> list[dict[str, list[str]]]:
        return self._loop.run_until_complete(self._generate_batch_async(database_records, tasks))

    async def _generate_batch_async(
        self, database_records: list[dict[str, str]], tasks: list[str]
    ) -> list[dict[str, list[str]]]:
        res_list = [{} for _ in database_records]
        jobs = []
        for i, record in enumerate(database_records):
            for task in tasks:
                if task not in self.task_templates:
                    print(f"Warning: Task '{task}' not found in task_prompts. Skipping.")
                    continue
                jobs.append((i, task, self._classify_one(record, task)))

        results = await asyncio.gather(*(job[2] for job in jobs))
        for (i, task, _), cls_value in zip(jobs, results):
            res_list[i][task] = cls_value
        return res_list

    async def _classify_one(self, database_record: dict[str, str], task: str) -> list[str]:
        try:
            prompt = self.task_templates[task].render(**database_record)
        except TemplateError as e:
            print(f"Warning: Failed to render prompt template for task '{task}': {e}. Skipping.")
            return []

        try:
            response_model = build_structured_output_model(task)
        except KeyError:
            print(f"Warning: Task '{task}' has no registered classes in TASK_CLASSES. Skipping.")
            return []

        try:
            async with self.semaphore:
                completion = await self.client.beta.chat.completions.parse(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    response_format=response_model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
        except openai.OpenAIError as e:
            print(f"Warning: API request for task '{task}' failed: {e}. Skipping.")
            return []

        message = completion.choices[0].message
        if message.refusal:
            print(f"Warning: Task '{task}' request was refused by the model: {message.refusal}")
            return []

        return message.parsed.cls



class LocalHFClassifierModel(Model):
    """Model that loads a converted, standard Hugging Face style multitask classification directory."""
    
    model_path: str = ConfigurableValue(
        desc="Path to the converted model directory containing config.json, pytorch_model.bin and heads.bin",
        user_default="converted_model/"
    )
    device: str = ConfigurableValue(
        desc="Device to load the model on (cpu, cuda, etc.)",
        user_default="cuda"
    )
    input_prompt: str = ConfigurableValue(
        desc="Jinja2 template for the input text. You can use any record fields.",
        user_default="{{ text }}"
    )
    threshold: float = ConfigurableValue(
        desc="Threshold for assignment of task classes",
        user_default=0.5
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._model = None
        self._tokenizer = None
        self.task_classes = {}
        self.jinja_env = Environment()
        self.input_prompt_template = self.jinja_env.from_string(self.input_prompt)

    def _init_model(self):
        if self._model is not None:
            return

        import torch
        import torch.nn as nn
        from transformers import AutoModel, AutoTokenizer

        config_path = os.path.join(self.model_path, "config.json")
        print(f"Loading configuration from '{config_path}'...")
        with open(config_path, "r") as f:
            config_data = json.load(f)
        self.task_classes = config_data.get("task_classes", {})  # FIXME: here could be a fallback to the global TASK_CLASSES, but I'm not sure we should not do that - the model should have its own task_classes defined in its config.json

        print(f"Loading tokenizer from '{self.model_path}'...")
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_path, trust_remote_code=True)

        class Head(nn.Module):
            def __init__(self, in_features, out_features):
                super().__init__()
                self.linear = nn.Linear(in_features, out_features)

        class CustomModel(nn.Module):
            def __init__(self, model_path, task_sizes):
                super().__init__()
                self.encoder = AutoModel.from_pretrained(model_path, trust_remote_code=True)
                self.heads = nn.ModuleDict({
                    task: Head(self.encoder.config.hidden_size, size)
                    for task, size in task_sizes.items()
                })

        task_sizes = {task: len(classes) for task, classes in self.task_classes.items()}

        print(f"Loading encoder model and classification heads...")
        py_model = CustomModel(self.model_path, task_sizes)
        
        heads_path = os.path.join(self.model_path, "heads.bin")
        print(f"Loading classification heads weights from '{heads_path}'...")
        py_model.heads.load_state_dict(torch.load(heads_path, map_location="cpu"))
        
        self._device = torch.device(self.device)
        py_model = py_model.to(self._device)
        py_model.eval()

        self._model = py_model

    def generate(self, database_record: dict[str, str], tasks: list[str]) -> dict[str, list[str]]:
        return self.generate_batch([database_record], tasks)[0]

    def generate_batch(self, database_records: list[dict[str, str]], tasks: list[str]) -> list[dict[str, list[str]]]:
        self._init_model()
        import torch

        prompts = [self.input_prompt_template.render(**record) for record in database_records]
        inputs = self._tokenizer(
            prompts, 
            return_tensors="pt", 
            padding=True, 
            truncation=True, 
            max_length=512
        )
        inputs = {k: v.to(self._device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._model.encoder(**inputs)
            cls_reprs = outputs.last_hidden_state[:, 0, :]
            
            res_list = [{} for _ in range(len(database_records))]
            for task in tasks:
                if task not in self._model.heads:
                    print(f"Warning: Task '{task}' not found in model heads. Skipping.")
                    continue
                logits = self._model.heads[task].linear(cls_reprs)
                prob = torch.sigmoid(logits)
                predictions = (
                    (prob > self.threshold) | (prob == prob.max(dim=-1, keepdim=True).values)
                ).tolist()
                
                classes = self.task_classes.get(task) or TASK_CLASSES.get(task)
                for i, pred_row in enumerate(predictions):
                    res_list[i][task] = [str(classes[j]) for j, pred in enumerate(pred_row) if pred]
            return res_list


def convert_lightning_checkpoint(
    checkpoint_path: str, 
    output_dir: str, 
    model_name: str = "jhu-clsp/mmBERT-base"
) -> None:
    """Convert a PyTorch Lightning checkpoint to a standard HF-style directory."""
    import torch
    from transformers import AutoTokenizer, AutoConfig
    
    print(f"Loading Lightning checkpoint from '{checkpoint_path}'...")
    ckpt = torch.load(checkpoint_path, map_location="cpu")
    state_dict = ckpt["state_dict"]
    
    encoder_state_dict = {}
    heads_state_dict = {}
    
    for k, v in state_dict.items():
        if k.startswith("model._orig_mod.encoder."):
            new_key = k[len("model._orig_mod.encoder."):]
            encoder_state_dict[new_key] = v
        elif k.startswith("model._orig_mod.heads."):
            new_key = k[len("model._orig_mod.heads."):]
            heads_state_dict[new_key] = v
            
    os.makedirs(output_dir, exist_ok=True)
    
    weights_path = os.path.join(output_dir, "pytorch_model.bin")
    print(f"Saving encoder weights to '{weights_path}'...")
    torch.save(encoder_state_dict, weights_path)
    
    heads_path = os.path.join(output_dir, "heads.bin")
    print(f"Saving classification heads to '{heads_path}'...")
    torch.save(heads_state_dict, heads_path)
    
    print(f"Downloading and saving tokenizer configs to '{output_dir}'...")
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    tokenizer.save_pretrained(output_dir)
    
    print(f"Building custom config.json in '{output_dir}'...")
    base_config = AutoConfig.from_pretrained(model_name, trust_remote_code=True)
    config_dict = base_config.to_dict()
    config_dict["task_classes"] = TASK_CLASSES
    config_dict["model_type_custom"] = "multitask_classifier"
    
    config_file_path = os.path.join(output_dir, "config.json")
    with open(config_file_path, "w") as f:
        json.dump(config_dict, f, indent=2)
        
    print(f"Conversion successfully completed! Model saved at '{output_dir}'.")
