# DML 확장

이 페이지에서는 CUBRID 전용 데이터 조작 언어(DML) 구문을 다룹니다: INSERT ... ON DUPLICATE KEY UPDATE, REPLACE INTO, FOR UPDATE.

## INSERT ... ON DUPLICATE KEY UPDATE

CUBRID는 upsert 작업을 위한 `ON DUPLICATE KEY UPDATE`를 지원합니다. `sqlalchemy_cubrid`의 CUBRID 전용 `insert()` 함수를 사용합니다:

```python
from sqlalchemy_cubrid import insert

stmt = insert(users).values(id=1, name="Alice", email="alice@example.com")
stmt = stmt.on_duplicate_key_update(
    name="Alice Updated",
    email="alice_new@example.com",
)

with engine.connect() as conn:
    conn.execute(stmt)
    conn.commit()
```

생성되는 SQL:

```sql
INSERT INTO users (id, name, email)
VALUES (?, ?, ?)
ON DUPLICATE KEY UPDATE name = ?, email = ?
```

!!! warning
    CUBRID는 ON DUPLICATE KEY UPDATE에서 `VALUES()` 함수를 지원**하지 않습니다** (MySQL과 다름). 명시적 값이나 컬럼 표현식을 전달해야 합니다. `stmt.inserted` 컬럼을 참조하지 마십시오 -- 리터럴 값을 사용하십시오.

### 딕셔너리 사용

```python
from sqlalchemy_cubrid import insert

stmt = insert(users).values(id=1, name="Alice", email="alice@example.com")
stmt = stmt.on_duplicate_key_update({
    "name": "Alice Updated",
    "email": "alice_new@example.com",
})
```

### 튜플 리스트 사용 (순서 보장)

```python
stmt = insert(users).values(id=1, name="Alice", email="alice@example.com")
stmt = stmt.on_duplicate_key_update([
    ("name", "Alice Updated"),
    ("email", "alice_new@example.com"),
])
```

### 컬럼 표현식 사용

```python
from sqlalchemy import literal

stmt = insert(users).values(id=1, name="Alice", email="alice@example.com")
stmt = stmt.on_duplicate_key_update(
    name=literal("Alice") + " (updated)",
)
```

## REPLACE INTO

`REPLACE INTO`는 중복 키가 있을 때 기존 행을 삭제하고 새 행을 삽입합니다. 이는 행을 제자리에서 수정하는 ON DUPLICATE KEY UPDATE와 다릅니다.

```python
from sqlalchemy_cubrid import replace

stmt = replace(users).values(id=1, name="Alice", email="alice@example.com")

with engine.connect() as conn:
    conn.execute(stmt)
    conn.commit()
```

생성되는 SQL:

```sql
REPLACE INTO users (id, name, email) VALUES (?, ?, ?)
```

!!! note
    `REPLACE INTO`는 먼저 기본 키 또는 유니크 인덱스에서 충돌하는 기존 행을 삭제한 다음 새 행을 삽입합니다. 이는 auto-increment 값이 변경될 수 있고 DELETE 트리거가 실행된다는 것을 의미합니다.

### 대량 교체

```python
from sqlalchemy_cubrid import replace

stmt = replace(users)

with engine.connect() as conn:
    conn.execute(stmt, [
        {"id": 1, "name": "Alice", "email": "alice@example.com"},
        {"id": 2, "name": "Bob", "email": "bob@example.com"},
        {"id": 3, "name": "Charlie", "email": "charlie@example.com"},
    ])
    conn.commit()
```

## FOR UPDATE

CUBRID는 행 수준 잠금을 위한 `SELECT ... FOR UPDATE`를 지원합니다. 표준 SQLAlchemy의 `with_for_update()`가 지원됩니다:

```python
from sqlalchemy import select

stmt = select(users).where(users.c.id == 1).with_for_update()

with engine.connect() as conn:
    row = conn.execute(stmt).first()
```

생성되는 SQL:

```sql
SELECT users.id, users.name, users.email
FROM users
WHERE users.id = ?
FOR UPDATE
```

### FOR UPDATE OF (컬럼 수준 잠금)

CUBRID는 특정 컬럼을 잠그는 `OF` 절을 지원합니다:

```python
stmt = (
    select(users)
    .where(users.c.id == 1)
    .with_for_update(of=[users.c.name, users.c.email])
)
```

생성되는 SQL:

```sql
SELECT users.id, users.name, users.email
FROM users
WHERE users.id = ?
FOR UPDATE OF name, email
```

### FOR SHARE (미지원)

!!! warning
    CUBRID는 `FOR SHARE` 또는 `LOCK IN SHARE MODE`를 지원**하지 않습니다**. `with_for_update(read=True)`를 사용하면 FOR UPDATE 절이 자동으로 생략됩니다.

```python
# FOR SHARE 절이 생성되지 않습니다 -- 자동으로 무시됩니다
stmt = select(users).with_for_update(read=True)
```

## TRUNCATE TABLE

CUBRID는 테이블의 모든 행을 효율적으로 제거하는 `TRUNCATE TABLE`을 지원합니다. dialect에서 커스텀 DDL element를 제공합니다:

```python
from sqlalchemy_cubrid import truncate

with engine.connect() as conn:
    conn.execute(truncate("my_table"))
    conn.commit()
```

생성되는 SQL:

```sql
TRUNCATE TABLE "my_table"
```

!!! note
    `TRUNCATE TABLE`은 개별 행 삭제를 기록하지 않으므로 `DELETE FROM`보다 빠릅니다. 단, 롤백이 불가능합니다 (CUBRID는 DDL을 자동 커밋).

## REGEXP / RLIKE 연산자

CUBRID는 정규 표현식 매칭을 위한 `REGEXP`와 `RLIKE`를 지원합니다. SQLAlchemy의 `regexp_match()`를 사용하세요:

```python
from sqlalchemy import select, column

stmt = select(column("name")).where(
    column("name").regexp_match(r"^[A-Z][a-z]+$")
)
```

생성되는 SQL:

```sql
SELECT name WHERE name REGEXP ?
```

부정(negation)도 지원됩니다:

```python
stmt = select(column("name")).where(
    ~column("name").regexp_match(r"^test")
)
```

## CAST 타입 매핑

`CAST()` 사용 시 dialect가 SQLAlchemy 타입을 CUBRID 네이티브 타입으로 자동 변환합니다:

```python
from sqlalchemy import cast, literal_column, Text, Boolean

# CAST(x AS TEXT) -> CAST(x AS STRING)
stmt = cast(literal_column("description"), Text)

# CAST(x AS BOOLEAN) -> CAST(x AS SMALLINT)
stmt = cast(literal_column("flag"), Boolean)
```

| SQLAlchemy 타입   | CUBRID CAST 타입 |
|-------------------|------------------|
| `Text`            | `STRING`         |
| `Boolean`         | `SMALLINT`       |
| `Float`           | `DOUBLE`         |
| `NCHAR`           | `CHAR`           |
| `NVARCHAR`        | `VARCHAR`        |
| `LargeBinary`     | `BIT VARYING`    |

## 임포트 참조

모든 CUBRID DML 구문은 최상위 패키지에서 임포트할 수 있습니다:

```python
from sqlalchemy_cubrid import insert, Insert, replace, Replace, truncate, Truncate
```

또는 `dml` 서브모듈에서:

```python
from sqlalchemy_cubrid.dml import insert, Insert, replace, Replace, truncate, Truncate
```
