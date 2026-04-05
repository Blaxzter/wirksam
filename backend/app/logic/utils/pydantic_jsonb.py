"""Generic JSONB TypeDecorator that auto-serializes Pydantic models.

Usage:
    from app.logic.utils.pydantic_jsonb import PydanticJSONB

    # Single model:
    sa_column=sa.Column(PydanticJSONB(MyModel), nullable=True)

    # List of models:
    sa_column=sa.Column(PydanticJSONB(MyModel, is_list=True), nullable=False, server_default="[]")
"""

from typing import Any

from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator


class PydanticJSONB(TypeDecorator[Any]):
    """JSONB column that auto-converts between Pydantic models and JSON.

    Args:
        model_class: The Pydantic BaseModel class to serialize/deserialize.
        is_list: If True, the column stores a JSON array of models.
                 If False, the column stores a single model object.
    """

    impl = JSONB
    cache_ok = True

    def __init__(self, model_class: type[BaseModel], *, is_list: bool = False) -> None:
        self.model_class = model_class
        self.is_list = is_list
        super().__init__()

    def process_bind_param(self, value: Any, dialect: Any) -> Any:  # noqa: ANN401
        if value is None:
            return [] if self.is_list else None
        if self.is_list:
            return [v.model_dump() if isinstance(v, BaseModel) else v for v in value]
        return value.model_dump() if isinstance(value, BaseModel) else value

    def process_result_value(self, value: Any, dialect: Any) -> Any:  # noqa: ANN401
        if value is None:
            return [] if self.is_list else None
        if self.is_list:
            return [
                v
                if isinstance(v, self.model_class)
                else self.model_class.model_validate(v)
                for v in value
            ]
        if isinstance(value, self.model_class):
            return value
        return self.model_class.model_validate(value)
