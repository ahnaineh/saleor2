import mimetypes
from typing import Any

import google.generativeai as genai
from django.conf import settings


class GeminiClient:
    """Client for interacting with Google's Gemini API."""

    def __init__(self):
        """Initialize the Gemini client with API key from settings."""
        api_key = getattr(settings, "GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not configured in settings")

        genai.configure(api_key=api_key)  # type: ignore  # noqa: PGH003

        # Base generation config
        self.base_config = {
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192,
            "response_mime_type": "text/plain",
        }

    def _get_model(
        self,
        model_name: str = "gemini-2.0-flash",
        generation_config: dict | None = None,
        system_instruction: str | None = None,
    ):
        """Get a Gemini model with the specified configuration."""
        config = generation_config or self.base_config

        if system_instruction:
            return genai.GenerativeModel(  # type: ignore  # noqa: PGH003
                model_name=model_name,
                generation_config=config,  # type: ignore  # noqa: PGH003
                system_instruction=system_instruction,
            )

        return genai.GenerativeModel(  # type: ignore  # noqa: PGH003
            model_name=model_name,
            generation_config=config,  # type: ignore  # noqa: PGH003
        )

    def _process_uploaded_file(self, file_path: str):
        """Process a file for use with Gemini API."""
        try:
            mime_type, _ = mimetypes.guess_type(file_path)

            if not mime_type:
                raise ValueError("Could not determine MIME type")

            gemini_file = genai.upload_file(file_path, mime_type=mime_type)  # type: ignore  # noqa: PGH003
            return gemini_file
        except Exception as e:
            raise ValueError(f"Error processing file: {str(e)}") from e

    def identify_hardware_from_image(self, image_path: str) -> str:
        """Identify hardware from an image file path."""
        try:
            gemini_file = self._process_uploaded_file(image_path)

            model = self._get_model(model_name="gemini-2.0-flash")

            response = model.generate_content(
                [
                    "What object is this? Describe how it might be used",
                    "Object: The input is a PC hardware Image (any hardware component related to computers)",
                    "Description: You are a computer parts expert. Identify PC hardware components from images, "
                    "including processors, graphics cards, motherboards, memory modules, storage devices, and PSUs. "
                    "Focus on specific characteristics like brand logos, form factors, and component features. "
                    "The output should only be the exact name of the device, for example, 'Intel Core i9-10900K' for a processor "
                    "or 'ASUS B560 Motherboard' for a motherboard. If given any other images simply reply with "
                    "'I cannot identify this as a PC hardware component'",
                    "Object: ",
                    gemini_file,
                    "",
                    "Description: ",
                ]
            )

            return response.text.strip()
        except Exception as e:
            return f"Error processing image: {str(e)}"

    def find_similar_products(
        self, image_path: str, product_database: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Find similar products based on an image file path."""
        try:
            gemini_file = self._process_uploaded_file(image_path)

            model = self._get_model(model_name="gemini-2.0-flash")

            # Convert our product database to a string format that Gemini can process
            products_string = "\n".join(
                f"Product ID: {p.get('id', '')}, Name: {p.get('name', '')}, "
                f"Category: {p.get('category', '')}, Description: {p.get('description', '')[:100]}..."
                for p in product_database
            )

            response = model.generate_content(
                [
                    "I have an image of a PC hardware component and a database of products. "
                    "Based on the image, identify the component and suggest the most similar products "
                    "from the database. Return the product IDs of the 3 most relevant matches.",
                    "Image: ",
                    gemini_file,
                    "Product Database:",
                    products_string,
                    "Most similar product IDs (comma separated):",
                ]
            )

            # Parse the response to get product IDs
            product_ids = [pid.strip() for pid in response.text.strip().split(",")]

            # Return the matching products from our database
            return [p for p in product_database if str(p.get("id", "")) in product_ids]
        except Exception as e:
            return []

    def hardware_chat(
        self, query: str, history: list[dict] | None = None
    ) -> dict[str, Any]:
        """Chat with Gemini about hardware."""
        try:
            system_instruction = (
                "Act as a professional computer consultant with expertise in both hardware and software. "
                "Provide accurate and up-to-date recommendations based on the latest technologies and best practices. "
                "Keep responses concise and answer only the question asked. "
                "Avoid unnecessary introductions or explanations unless explicitly requested by the user. "
                "If clarification is needed, ask a short follow-up question. "
                "Anything not related to computers respond with 'I can't answer that!'"
            )

            model = self._get_model(
                model_name="gemini-2.0-flash", system_instruction=system_instruction
            )

            if history:
                chat = model.start_chat(history=history)
                response = chat.send_message(query)
            else:
                response = model.generate_content(query)

            return {
                "response": response.text.strip(),
                "history": history
                + [
                    {"role": "user", "parts": [query]},
                    {"role": "model", "parts": [response.text.strip()]},
                ]
                if history
                else [
                    {"role": "user", "parts": [query]},
                    {"role": "model", "parts": [response.text.strip()]},
                ],
            }
        except Exception as e:
            return {
                "response": f"Error processing query: {str(e)}",
                "history": history or [],
            }
