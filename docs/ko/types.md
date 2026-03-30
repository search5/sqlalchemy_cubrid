# 타입 시스템

이 페이지에서는 CUBRID 데이터 타입이 SQLAlchemy 타입에 어떻게 매핑되는지, 특수 매핑과 CUBRID 고유 동작을 포함하여 설명합니다.

## 타입 매핑 표

### 숫자 타입

| CUBRID 타입 | SQLAlchemy 타입 | 비고 |
|-------------|-----------------|------|
| `INTEGER` / `INT`  | `Integer`             | 32비트 부호 있는 정수 |
| `BIGINT`           | `BigInteger`          | 64비트 부호 있는 정수 |
| `SHORT` / `SMALLINT` | `SmallInteger`     | 16비트 부호 있는 정수. SHOW COLUMNS는 `SHORT`으로 표시 |
| `FLOAT` / `REAL`   | `Float`               | 단정밀도 (유효숫자 7자리) |
| `DOUBLE`           | `Double`              | 배정밀도 |
| `NUMERIC` / `DECIMAL` | `Numeric`          | 정밀도와 스케일을 가진 정확한 숫자 |

### 문자열 타입

| CUBRID 타입 | SQLAlchemy 타입 | 비고 |
|-------------|-----------------|------|
| `CHAR` / `CHARACTER`           | `CHAR`          | 고정 길이 문자열 |
| `VARCHAR` / `CHARACTER VARYING`| `VARCHAR`       | 가변 길이 문자열 |
| `STRING`                       | `VARCHAR`       | `VARCHAR(1,073,741,823)`의 별칭 |

### 날짜/시간 타입

| CUBRID 타입 | SQLAlchemy 타입 | 비고 |
|-------------|-----------------|------|
| `DATE`           | `Date`          | 날짜만 (시간 구성 요소 없음) |
| `TIME`           | `Time`          | 시간만 (날짜 구성 요소 없음) |
| `DATETIME`       | `DateTime`      | 날짜 + 시간, **밀리초** 정밀도 |
| `TIMESTAMP`      | `TIMESTAMP`     | Unix 타임스탬프 |
| `DATETIMELTZ`    | `DateTime`      | 로컬 타임존 포함 DATETIME |
| `DATETIMETZ`     | `DateTime`      | 명시적 타임존 포함 DATETIME |
| `TIMESTAMPLTZ`   | `TIMESTAMP`     | 로컬 타임존 포함 TIMESTAMP |
| `TIMESTAMPTZ`    | `TIMESTAMP`     | 명시적 타임존 포함 TIMESTAMP |

!!! warning
    CUBRID DATETIME은 **밀리초** (3자리) 정밀도를 가지며, MySQL이나 PostgreSQL의 마이크로초 (6자리) 정밀도가 아닙니다. 애플리케이션이 마이크로초 정밀도에 의존하는 경우 데이터 손실이 발생합니다.

### 바이너리 타입

| CUBRID 타입 | SQLAlchemy 타입 | 비고 |
|-------------|-----------------|------|
| `BIT`          | `LargeBinary`    | 고정 길이 바이너리 |
| `BIT VARYING`  | `LargeBinary`    | 가변 길이 바이너리 |
| `BLOB`         | `BLOB`           | Binary Large Object |
| `CLOB`         | `CLOB`           | Character Large Object |

### 기타 타입

| CUBRID 타입 | SQLAlchemy 타입 | 비고 |
|-------------|-----------------|------|
| `ENUM`       | `Enum`          | 최대 512개 값 |
| `JSON`       | `JSON`          | CUBRID 10.2부터 사용 가능 |
| `SET`        | `NullType`      | 완전한 지원을 위해 `CubridSet` 사용 |
| `MULTISET`   | `NullType`      | 완전한 지원을 위해 `CubridMultiset` 사용 |
| `LIST` / `SEQUENCE` | `NullType` | 완전한 지원을 위해 `CubridList` 사용 |

## 특수 타입 매핑

CUBRID 타입 컴파일러는 CUBRID에 존재하지 않는 타입에 대해 여러 매핑을 적용합니다.

### BOOLEAN에서 SMALLINT로

CUBRID에는 `BOOLEAN` 컬럼 타입이 없습니다 (JSON 내부에서만 존재). dialect는 `Boolean`을 `SMALLINT`로 매핑합니다:

```python
from sqlalchemy import Column, Boolean

class MyTable(Base):
    __tablename__ = "my_table"
    id = Column(Integer, primary_key=True)
    active = Column(Boolean)
    # DDL: active SMALLINT
```

### TEXT에서 STRING으로

CUBRID에는 `TEXT` 타입이 없습니다. dialect는 `Text`를 `STRING` (`VARCHAR(1,073,741,823)`)으로 매핑합니다:

```python
from sqlalchemy import Column, Text

class Article(Base):
    __tablename__ = "articles"
    id = Column(Integer, primary_key=True)
    body = Column(Text)
    # DDL: body STRING
```

### NCHAR에서 CHAR로

`NCHAR`과 `NCHAR VARYING`은 CUBRID 9.0에서 제거되었습니다. dialect는 이를 `CHAR`과 `VARCHAR`로 매핑합니다:

```python
from sqlalchemy import Column, Unicode, UnicodeText

class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True)
    title = Column(Unicode(100))   # DDL: title VARCHAR(100)
    body = Column(UnicodeText)     # DDL: body STRING
```

### Float()에서 DOUBLE로

정밀도가 지정되지 않은 일반 `Float()`는 더 나은 정확도를 위해 `DOUBLE`로 매핑됩니다. 특정 정밀도가 주어지고 7 이하이면 `FLOAT`로 매핑됩니다. 정밀도가 7을 초과하면 CUBRID가 자동으로 `DOUBLE`로 승격합니다:

```python
from sqlalchemy import Column, Float, Double

class Measurement(Base):
    __tablename__ = "measurements"
    id = Column(Integer, primary_key=True)
    approx = Column(Float)            # DDL: DOUBLE
    precise = Column(Float(5))        # DDL: FLOAT
    big_precise = Column(Float(10))   # DDL: DOUBLE (p > 7)
    explicit = Column(Double)         # DDL: DOUBLE
```

### LargeBinary에서 BIT VARYING으로

SQLAlchemy의 `LargeBinary`는 인라인 바이너리 저장을 위해 `BIT VARYING(1073741823)`로 매핑됩니다:

```python
from sqlalchemy import Column, LargeBinary

class FileStore(Base):
    __tablename__ = "files"
    id = Column(Integer, primary_key=True)
    data = Column(LargeBinary)
    # DDL: data BIT VARYING(1073741823)
```

## 컬렉션 타입

CUBRID는 사용자 정의 SQLAlchemy 타입을 통해 매핑되는 세 가지 컬렉션 타입을 제공합니다. 자세한 내용은 [CUBRID 기능](cubrid-features.md) 페이지를 참조하십시오.

```python
from sqlalchemy_cubrid.types import CubridSet, CubridMultiset, CubridList

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    tags = Column(CubridSet("VARCHAR(50)"))
    # DDL: tags SET_OF(VARCHAR(50))
```

## CUBRID OID 타입

객체-관계형 참조를 위해 `CubridOID`를 사용합니다. [CUBRID 기능](cubrid-features.md)을 참조하십시오.

```python
from sqlalchemy_cubrid.oid import CubridOID

class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True)
    manager = Column(CubridOID("person"))
    # DDL: manager person
```

## JSON 타입

CUBRID는 버전 10.2부터 JSON을 지원합니다. 표준 SQLAlchemy `JSON`이 바로 작동합니다:

```python
from sqlalchemy import Column, JSON

class Config(Base):
    __tablename__ = "configs"
    id = Column(Integer, primary_key=True)
    data = Column(JSON)
    # DDL: data JSON
```

엔진 생성 시 사용자 정의 직렬화기를 설정할 수 있습니다:

```python
engine = create_engine(
    "cubrid://dba:@localhost:33000/testdb",
    json_serializer=my_serializer,
    json_deserializer=my_deserializer,
)
```

## ENUM 타입

CUBRID는 최대 512개 값을 가진 ENUM을 지원합니다:

```python
from sqlalchemy import Column, Enum

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    status = Column(Enum("pending", "shipped", "delivered"))
    # DDL: status ENUM('pending', 'shipped', 'delivered')
```

## 인트로스펙션 타입 파싱

테이블을 리플렉션할 때 dialect는 CUBRID의 `SHOW COLUMNS` 출력을 파싱하여 타입 문자열을 SQLAlchemy 타입으로 매핑합니다. 주요 파싱 동작:

- `SHORT`는 `SmallInteger`로 매핑됩니다 (CUBRID는 `SMALLINT` 대신 `SHORT`로 보고)
- `INTEGER`는 `Integer`로 매핑됩니다 (CUBRID는 `INT` 대신 `INTEGER`로 보고)
- `NUMERIC(p,s)`에서 정밀도와 스케일을 추출합니다
- `VARCHAR(n)`에서 길이를 추출합니다
- `ENUM('a','b','c')`에서 열거형 값을 추출합니다
- `FLOAT(p)`에서 정밀도를 추출합니다
- 컬렉션 타입 (`SET_OF`, `MULTISET_OF`, `LIST_OF`, `SEQUENCE_OF`)은 리플렉션 시 `NullType`으로 매핑됩니다 (완전한 컬렉션 지원을 위해 명시적 컬럼 타입을 사용하십시오)
