from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=12, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized_email = value.strip().lower()
        if "@" not in normalized_email:
            raise ValueError("Email must contain '@'.")

        return normalized_email

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        has_letter = any(character.isalpha() for character in value)
        has_digit_or_symbol = any(
            not character.isalpha()
            for character in value
        )
        if not has_letter or not has_digit_or_symbol:
            raise ValueError(
                "Password must include letters and at least one number or symbol."
            )

        return value


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized_email = value.strip().lower()
        if "@" not in normalized_email:
            raise ValueError("Email must contain '@'.")

        return normalized_email


class UserResponse(BaseModel):
    id: int
    email: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
