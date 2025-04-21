import uuid

import graphene
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from ...hardware.gemini_client import GeminiClient
from ...hardware.models import (
    HardwareChat,
    HardwareIdentification,
    HardwareQuery,
    ProductSimilaritySearch,
)
from ...permission.enums import AppPermission, HardwarePermissions
from ...product.models import Product
from ..core.doc_category import DOC_CATEGORY_PRODUCTS
from ..core.fields import BaseField
from ..core.mutations import BaseMutation
from ..core.scalars import DateTime
from ..core.types import BaseInputObjectType, Upload
from ..core.types.common import Error
from ..product.types import Product as ProductType


class HardwareError(Error):
    code = graphene.String(description="Error code for hardware related errors.")

    class Meta:
        description = (
            "Represents errors related to hardware identification and chatbot features."
        )
        doc_category = DOC_CATEGORY_PRODUCTS


# Types
class HardwareIdentificationType(graphene.ObjectType):
    id = graphene.GlobalID(required=True)
    image = graphene.String()
    result = graphene.String()
    created_at = DateTime()

    class Meta:
        description = "Represents a hardware identification result."
        doc_category = DOC_CATEGORY_PRODUCTS


class HardwareQueryType(graphene.ObjectType):
    id = graphene.GlobalID(required=True)
    question = graphene.String()
    answer = graphene.String()
    created_at = DateTime()

    class Meta:
        description = "Represents a question and answer in a hardware chat session."
        doc_category = DOC_CATEGORY_PRODUCTS


class HardwareChatType(graphene.ObjectType):
    id = graphene.GlobalID(required=True)
    session_id = graphene.String()
    queries = graphene.List(HardwareQueryType)
    created_at = DateTime()
    updated_at = DateTime()

    class Meta:
        description = "Represents a hardware chat session."
        doc_category = DOC_CATEGORY_PRODUCTS

    def resolve_queries(self, info):
        return HardwareQuery.objects.filter(chat_id=self.id)


class ProductSimilaritySearchType(graphene.ObjectType):
    id = graphene.GlobalID(required=True)
    image = graphene.String()
    identified_component = graphene.String()
    similar_products = graphene.List(ProductType)
    created_at = DateTime()

    class Meta:
        description = "Represents a search for similar products based on an image."
        doc_category = DOC_CATEGORY_PRODUCTS

    def resolve_similar_products(self, info):
        product_ids = self.similar_product_ids
        return Product.objects.filter(id__in=product_ids)


# Inputs
class HardwareChatMessageInput(BaseInputObjectType):
    session_id = graphene.String(
        description="Session ID for continuing a conversation. Leave empty for a new session."
    )
    query = graphene.String(
        required=True, description="The hardware-related query to ask."
    )

    class Meta:
        doc_category = DOC_CATEGORY_PRODUCTS


class FindSimilarProductsInput(BaseInputObjectType):
    category_id = graphene.ID(
        description="Optional category ID to limit the search scope."
    )
    max_results = graphene.Int(
        default_value=3, description="Maximum number of similar products to return."
    )

    class Meta:
        doc_category = DOC_CATEGORY_PRODUCTS


# Mutations
class IdentifyHardwareImage(BaseMutation):
    identification = graphene.Field(HardwareIdentificationType)

    class Arguments:
        image = Upload(
            required=True, description="Image file to identify hardware from."
        )

    class Meta:
        description = "Identify hardware from an uploaded image."
        doc_category = DOC_CATEGORY_PRODUCTS
        # permissions = (HardwarePermissions.CHAT,)
        error_type_class = HardwareError
        error_type_field = "hardware_errors"

    @classmethod
    def perform_mutation(cls, _root, info, /, *, image):
        # Save the uploaded file
        image_file = info.context.FILES[image]
        image_name = f"{uuid.uuid4()}_{image_file.name}"
        path = default_storage.save(f"hw/{image_name}", ContentFile(image_file.read()))

        # Get the full path to the saved file
        full_path = default_storage.path(path)

        # Process with Gemini
        client = GeminiClient()
        result = client.identify_hardware_from_image(full_path)

        # Store in database
        identification = HardwareIdentification.objects.create(
            image=path, result=result
        )

        return IdentifyHardwareImage(identification=identification)


class HardwareChatMessage(BaseMutation):
    chat = graphene.Field(HardwareChatType)
    response = graphene.String()

    class Arguments:
        input = HardwareChatMessageInput(
            required=True, description="Fields required for the hardware chat."
        )

    class Meta:
        description = "Chat with the hardware expert about hardware-related topics."
        doc_category = DOC_CATEGORY_PRODUCTS
        # permissions = (HardwarePermissions.CHAT,)
        error_type_class = HardwareError
        error_type_field = "hardware_errors"

    @classmethod
    def perform_mutation(cls, _root, info, /, *, input):
        session_id = input.get("session_id")
        query = input.get("query")

        client = GeminiClient()

        if session_id:
            print(f"Session ID: {session_id}")
            try:
                chat_session = HardwareChat.objects.get(session_id=session_id)
                history = chat_session.history
                print(f"History: {history}")
            except HardwareChat.DoesNotExist:
                print(f"Session ID {session_id} does not exist.")
                print(HardwareChat.objects.all())
                chat_session = HardwareChat.objects.create(
                    session_id=str(uuid.uuid4()), history=[]
                )
                print(f"Creating new session. f{chat_session.session_id}")
                history = []
        else:
            chat_session = HardwareChat.objects.create(
                session_id=str(uuid.uuid4()), history=[]
            )
            history = []

        # Process the query with Gemini
        result = client.hardware_chat(query, history)

        # Update the chat session history
        chat_session.history = result["history"]
        chat_session.save()

        # Store the query and answer
        HardwareQuery.objects.create(
            chat=chat_session, question=query, answer=result["response"]
        )

        return HardwareChatMessage(chat=chat_session, response=result["response"])


class FindSimilarProducts(BaseMutation):
    product_search = graphene.Field(ProductSimilaritySearchType)
    similar_products = graphene.List(ProductType)

    class Arguments:
        image = Upload(
            required=True, description="Image file to search similar products for."
        )
        input = FindSimilarProductsInput(
            required=True, description="Fields required for finding similar products."
        )

    class Meta:
        description = "Find similar products based on an uploaded hardware image."
        doc_category = DOC_CATEGORY_PRODUCTS
        # permissions = (HardwarePermissions.CHAT,)
        error_type_class = HardwareError
        error_type_field = "hardware_errors"

    @classmethod
    def perform_mutation(cls, _root, info, /, *, image, input):
        image_file = info.context.FILES[image]
        image_name = f"{uuid.uuid4()}.{image_file.name.split('.')[-1]}"
        path = default_storage.save(
            f"pss/{image_name}", ContentFile(image_file.read())
        )

        # Get the full path to the saved file
        full_path = default_storage.path(path)

        category_id = input.get("category_id")
        max_results = input.get("max_results", 3)

        # Get products from the database
        products_query = Product.objects.all()

        if category_id:
            products_query = products_query.filter(category_id=category_id)

        # Convert products to a format suitable for Gemini
        product_database = []
        for product in products_query:
            product_database.append(
                {
                    "id": str(product.id),  # type: ignore  # noqa: PGH003
                    "name": product.name,
                    "category": product.category.name if product.category else "",
                    "description": product.description,
                }
            )

        client = GeminiClient()

        # First identify the hardware component
        hardware_id_result = client.identify_hardware_from_image(full_path)

        # Then find similar products
        similar_products_data = client.find_similar_products(
            full_path, product_database
        )

        # Limit the number of results
        similar_products_data = similar_products_data[:max_results]

        # Get product IDs for storage
        product_ids = [item.get("id") for item in similar_products_data]

        # Store the search in the database
        product_search = ProductSimilaritySearch.objects.create(
            image=path,
            identified_component=hardware_id_result,
            similar_product_ids=product_ids,
        )

        # Get the actual Product objects
        similar_products = Product.objects.filter(id__in=product_ids)

        return FindSimilarProducts(
            product_search=product_search, similar_products=list(similar_products)
        )


class HardwareQueries(graphene.ObjectType):
    hardware_identification = BaseField(
        HardwareIdentificationType,
        description="Get a specific hardware identification by ID.",
        args={"id": graphene.ID(required=True)},
    )

    hardware_identifications = BaseField(
        graphene.List(HardwareIdentificationType),
        description="List all hardware identifications.",
    )

    hardware_chat = BaseField(
        HardwareChatType,
        description="Get a specific hardware chat session by session ID.",
        args={"session_id": graphene.String(required=True)},
    )

    hardware_chats = BaseField(
        graphene.List(HardwareChatType),
        description="List all hardware chat sessions.",
    )

    product_similarity_search = BaseField(
        ProductSimilaritySearchType,
        description="Get a specific product similarity search by ID.",
        args={"id": graphene.ID(required=True)},
    )

    product_similarity_searches = BaseField(
        graphene.List(ProductSimilaritySearchType),
        description="List all product similarity searches.",
    )

    @staticmethod
    def resolve_hardware_identification(_root, _info, id):
        return HardwareIdentification.objects.filter(pk=id).first()

    @staticmethod
    def resolve_hardware_identifications(_root, _info):
        return HardwareIdentification.objects.all()

    @staticmethod
    def resolve_hardware_chat(_root, _info, session_id):
        return HardwareChat.objects.filter(session_id=session_id).first()

    @staticmethod
    def resolve_hardware_chats(_root, _info):
        return HardwareChat.objects.all()

    @staticmethod
    def resolve_product_similarity_search(_root, _info, id):
        return ProductSimilaritySearch.objects.filter(pk=id).first()

    @staticmethod
    def resolve_product_similarity_searches(_root, _info):
        return ProductSimilaritySearch.objects.all()


class HardwareMutations(graphene.ObjectType):
    identify_hardware_image = IdentifyHardwareImage.Field()
    hardware_chat_message = HardwareChatMessage.Field()
    find_similar_products = FindSimilarProducts.Field()
