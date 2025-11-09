"""MLX model wrapper for Qwen."""

from typing import Dict, Any, Optional
import mlx.core as mx
from mlx_lm import load, generate

from ..common.logger import logger


class QwenModel:
    """Wrapper for Qwen-MLX model."""

    def __init__(
        self,
        model_name: str = "Qwen/Qwen2.5-7B-Instruct",
        quantization: str = "4bit",
        max_tokens: int = 4096,
        temperature: float = 0.7
    ):
        """
        Initialize Qwen model.

        Args:
            model_name: Name of the Qwen model to use
            quantization: Quantization mode (4bit, 8bit, none)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
        """
        self.model_name = model_name
        self.quantization = quantization
        self.max_tokens = max_tokens
        self.temperature = temperature

        self.model = None
        self.tokenizer = None

        logger.info(f"Initializing Qwen model: {model_name}")

    def load_model(self):
        """Load the model and tokenizer."""
        if self.model is not None:
            return

        try:
            logger.info(f"Loading {self.model_name} with {self.quantization} quantization")

            # Determine quantization config
            quantize = None
            if self.quantization == "4bit":
                quantize = True  # MLX-LM uses 4-bit by default
            elif self.quantization == "8bit":
                quantize = True  # Can be configured via model config
            # else: no quantization

            # Load model and tokenizer
            self.model, self.tokenizer = load(
                self.model_name,
                tokenizer_config={"trust_remote_code": True}
            )

            logger.info("Model loaded successfully")

        except Exception as e:
            logger.error(f"Error loading model: {e}")
            raise

    def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> str:
        """
        Generate text from prompt.

        Args:
            prompt: Input prompt
            max_tokens: Override max tokens
            temperature: Override temperature

        Returns:
            Generated text
        """
        if self.model is None:
            self.load_model()

        max_tokens = max_tokens or self.max_tokens
        temperature = temperature or self.temperature

        try:
            # Format prompt with chat template
            messages = [
                {"role": "system", "content": "You are a helpful database optimization assistant."},
                {"role": "user", "content": prompt}
            ]

            formatted_prompt = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )

            # Generate response
            response = generate(
                self.model,
                self.tokenizer,
                prompt=formatted_prompt,
                max_tokens=max_tokens,
                temp=temperature,
                verbose=False
            )

            return response

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            raise

    def unload_model(self):
        """Unload model to free memory."""
        self.model = None
        self.tokenizer = None
        mx.metal.clear_cache()
        logger.info("Model unloaded")
