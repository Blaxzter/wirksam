# FastAPI Backend - Product Implementation Guide

## Overview

This guide provides instructions for implementing new products/features in the FastAPI backend using SQLModel, CRUD patterns, and FastAPI best practices.

## Architecture Overview

```
Backend Architecture:
├── Models (SQLModel)      → Database layer
├── Schemas (Pydantic)     → Data validation & serialization
├── CRUD (Operations)      → Database operations
├── API Routes (FastAPI)   → HTTP endpoints
├── Logic (Business)       → Business logic & services
└── Core (Config/Auth)     → Cross-cutting concerns
```

## Implementation Steps

### 1. Define the Data Model (SQLModel)

**Location**: `backend/app/models/`

Create your database model inheriting from the appropriate base class:

```python
# app/models/product.py
from sqlmodel import Field, Relationship
from app.models.base import Base, SoftDeleteBase
import uuid


class Product(Base, table=True):
    __tablename__ = "products"

    name: str = Field(index=True, description="Product name")
    description: str | None = Field(default=None)
    price: float = Field(description="Product price")
    sku: str = Field(unique=True, index=True)
    stock_quantity: int = Field(default=0)
    is_active: bool = Field(default=True)

    # Relationships
    categories: list["Category"] = Relationship(
        back_populates="products", link_table="product_categories"
    )


class ProductCategory(Base, table=True):
    __tablename__ = "product_categories"
    product_id: uuid.UUID = Field(foreign_key="products.id", primary_key=True)
    category_id: uuid.UUID = Field(foreign_key="categories.id", primary_key=True)


class Category(Base, table=True):
    __tablename__ = "categories"
    name: str = Field(unique=True, index=True)
    description: str | None = None
    products: list[Product] = Relationship(
        back_populates="categories", link_table="product_categories"
    )
```

**Key Patterns:**

- Inherit from `Base` for standard models, `SoftDeleteBase` for soft-delete
- Use `Field()` for column configuration
- Use `Relationship()` for associations
- Always include `__tablename__`

### 2. Create Database Schemas (Pydantic)

**Location**: `backend/app/schemas/`

```python
# app/schemas/product.py
from pydantic import BaseModel, Field, validator
import uuid


class ProductBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    price: float = Field(..., gt=0)
    sku: str = Field(..., min_length=1, max_length=100)
    stock_quantity: int = Field(0, ge=0)
    is_active: bool = True


class ProductCreate(ProductBase):
    category_ids: list[uuid.UUID] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    # ... other optional fields


class ProductResponse(ProductBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    categories: list["CategoryResponse"] = []

    class Config:
        from_attributes = True


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    total: int
    page: int
    per_page: int
    pages: int
```

### 3. Implement CRUD Operations

**Location**: `backend/app/crud/`

```python
# app/crud/product.py
from app.crud.base import CRUDBase
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate


class CRUDProduct(CRUDBase[Product, ProductCreate, ProductUpdate]):
    async def get_by_sku(self, session: AsyncSession, *, sku: str) -> Product | None:
        result = await session.execute(
            select(Product).where(Product.sku == sku.upper())
        )
        return result.scalars().first()

    async def create_with_categories(
        self, session: AsyncSession, *, obj_in: ProductCreate
    ) -> Product:
        # Create product and handle category associations
        product_data = obj_in.model_dump(exclude={"category_ids"})
        product = Product(**product_data)
        session.add(product)
        await session.flush()

        # Add category links...
        await session.commit()
        return product


product = CRUDProduct(Product)
```

### 4. Create API Routes

**Location**: `backend/app/api/routes/`

```python
# app/api/routes/products.py
from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.deps import DBDep, auth0

router = APIRouter(prefix="/products", tags=["products"])

@router.get("/", response_model=ProductListResponse)
async def get_products(
    session: DBDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100)
) -> Any:
    # Implementation...

@router.post("/", response_model=ProductResponse, status_code=201)
async def create_product(
    product_in: ProductCreate,
    session: DBDep,
    claims: dict = Depends(auth0.require_auth())
) -> Any:
    # Implementation with Auth0 user context...
```

### 5. Register Routes

**Location**: `backend/app/api/api.py`

```python
from app.api.routes import products

api_router.include_router(products.router, prefix="/api/v1")
```

### 6. Database Migration

```bash
# Create and apply migration
docker compose exec backend bash
alembic revision --autogenerate -m "Add Product models"
alembic upgrade head
```

## Auth0 Integration Patterns

### Working with Auth0 Claims

```python
# Common Auth0 claim fields
user_id = claims.get("sub")  # Unique Auth0 user ID
user_email = claims.get("email")  # User email address
user_roles = claims.get("https://your-domain.com/roles", [])  # Custom roles
```

### User Tracking in Models

```python
class Product(Base, table=True):
    # ... other fields ...
    created_by: str | None = Field(default=None)
    updated_by: str | None = Field(default=None)
```

### Authorization Patterns

```python
def require_admin_role(claims: dict = Depends(auth0.require_auth())):
    user_roles = claims.get("https://your-domain.com/roles", [])
    if "admin" not in user_roles:
        raise HTTPException(status_code=403, detail="Admin role required")
    return claims
```

## Testing

### Unit Tests

```python
# tests/crud/test_product.py
@pytest.mark.asyncio
async def test_create_product(session):
    product_in = ProductCreate(name="Test", price=99.99, sku="TEST001")
    product = await crud_product.create(session, obj_in=product_in)
    assert product.name == "Test"
```

### API Tests

```python
# tests/api/test_products.py
@pytest.mark.asyncio
async def test_create_product(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/v1/products/", json=product_data, headers=auth_headers
    )
    assert response.status_code == 201
```

## Best Practices

### 1. Model Design

- Use descriptive field names with descriptions
- Include proper indexes for queried fields
- Implement relationships with proper back_populates

### 2. Schema Validation

- Separate Create, Update, and Response schemas
- Use Pydantic validators for custom validation
- Use Field() for documentation and constraints

### 3. CRUD Operations

- Extend base CRUD class for type safety
- Add domain-specific methods
- Use proper error handling

### 4. API Design

- Follow REST conventions
- Use appropriate HTTP status codes
- Implement pagination for list endpoints
- Use dependency injection for auth and database

### 5. Security

- Always validate input data
- Use auth dependencies for protected endpoints
- Implement proper authorization checks

## Integration with Frontend

After implementing the backend:

1. Restart the backend server
2. Run: `pnpm run generate-client` in frontend
3. New API endpoints are available in the generated client

This ensures type-safe communication with automatic synchronization.
