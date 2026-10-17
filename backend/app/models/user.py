from pydantic import BaseModel, Field, GetCoreSchemaHandler
from pydantic_core import core_schema
from typing import Optional, List, Literal, Any
from datetime import datetime
from bson import ObjectId

class PyObjectId(ObjectId):
    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        def validate(v: str) -> ObjectId:
            if not ObjectId.is_valid(v):
                raise ValueError("Invalid ObjectId")
            return ObjectId(v)

        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.union_schema(
                [
                    core_schema.is_instance_schema(ObjectId),
                    core_schema.chain_schema([core_schema.str_schema(), core_schema.no_info_plain_validator_function(validate)])
                ]
            ),
            serialization=core_schema.plain_serializer_function_ser_schema(str),
        )

# --- Token Models ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    phone_number: Optional[str] = None

class DailyReminder(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    medicine_name: str
    timings: List[Literal["morning", "afternoon", "evening"]]
    is_active: bool = True

class RefillReminder(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    medicine_name: str
    initial_quantity: int
    frequency_per_day: int
    start_date: datetime = Field(default_factory=datetime.now)
    refill_date: datetime
    celery_task_id: str
    is_active: bool = True

class UserBase(BaseModel):
    name: str
    phone_number: str = Field(..., pattern=r"^\+[1-9]\d{1,14}$")
    age: Optional[int] = Field(None, gt=0)
    gender: Optional[str] = None

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=72)

class UserInDB(UserBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.now)
    daily_reminders: List[DailyReminder] = []
    refill_reminders: List[RefillReminder] = []

    class Config:
        json_encoders = {ObjectId: str}
        arbitrary_types_allowed = True


class UserPublic(UserBase):
    """Fields that may be returned when a user reads their own profile."""

    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    created_at: datetime = Field(default_factory=datetime.now)
    daily_reminders: List[DailyReminder] = []
    refill_reminders: List[RefillReminder] = []

    class Config:
        json_encoders = {ObjectId: str}
        arbitrary_types_allowed = True
