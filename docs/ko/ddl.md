# DDL

이 페이지에서는 데이터 정의 언어(DDL) 작업을 다룹니다: 테이블 생성 및 삭제, AUTO_INCREMENT, SERIAL (시퀀스), 인덱스, 테이블/컬럼 코멘트.

## CREATE TABLE 및 DROP TABLE

표준 SQLAlchemy 테이블 정의가 정상적으로 작동합니다:

```python
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String

engine = create_engine("cubrid://dba:@localhost:33000/testdb")
metadata = MetaData()

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), nullable=False),
    Column("email", String(200)),
)

# CREATE TABLE
metadata.create_all(engine)

# DROP TABLE
metadata.drop_all(engine)
```

## AUTO_INCREMENT

CUBRID는 정수 기본 키 컬럼에서 `AUTO_INCREMENT`를 지원합니다. MySQL과의 중요한 차이점:

!!! warning
    - CUBRID는 테이블당 AUTO_INCREMENT 컬럼을 **하나만** 허용합니다.
    - AUTO_INCREMENT는 UNIQUE 인덱스를 **자동으로 생성하지 않습니다**. 필요한 경우 유일성을 명시적으로 추가해야 합니다.

```python
users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100)),
)
```

생성되는 DDL:

```sql
CREATE TABLE users (
    id INTEGER AUTO_INCREMENT,
    name VARCHAR(100),
    PRIMARY KEY (id)
)
```

### 시드와 증가값을 가진 AUTO_INCREMENT

CUBRID는 `AUTO_INCREMENT(seed, increment)` 구문을 지원합니다. SQLAlchemy의 `Identity`는 AUTO_INCREMENT로 렌더링됩니다:

```python
from sqlalchemy import Identity

Table(
    "counters", metadata,
    Column("id", Integer, Identity(start=100, increment=10), primary_key=True),
)
```

!!! note
    CUBRID에는 SQL 표준의 `GENERATED AS IDENTITY`가 없으므로 `Identity()` 구문은 DDL에서 `AUTO_INCREMENT`로 매핑됩니다.

### 시퀀스 기반 기본값

컬럼에 `Sequence` 기본값이 있으면 AUTO_INCREMENT가 억제되고 대신 시리얼이 사용됩니다:

```python
from sqlalchemy import Sequence

my_seq = Sequence("my_seq", start=1)

Table(
    "items", metadata,
    Column("id", Integer, my_seq, primary_key=True),
)
```

## DONT_REUSE_OID 테이블 옵션

CUBRID는 버전 10.x부터 `REUSE_OID`가 기본값입니다. OID 컬럼으로 참조 가능한 테이블을 만들려면 (객체-관계형 참조를 위해) `cubrid_dont_reuse_oid` dialect 옵션을 사용합니다:

```python
person = Table(
    "person", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(50)),
    cubrid_dont_reuse_oid=True,
)
```

생성되는 DDL:

```sql
CREATE TABLE person (
    id INTEGER AUTO_INCREMENT,
    name VARCHAR(50),
    PRIMARY KEY (id)
) DONT_REUSE_OID
```

## SERIAL (시퀀스)

CUBRID는 SQL 표준의 `SEQUENCE` 대신 `SERIAL`을 사용합니다. dialect는 SQLAlchemy의 `Sequence` 구문을 `CREATE SERIAL` / `DROP SERIAL`로 자동 변환합니다.

### 시리얼 생성

```python
from sqlalchemy import Sequence

my_serial = Sequence("my_serial", start=1, increment=1)
metadata.create_all(engine)  # CREATE SERIAL my_serial START WITH 1 INCREMENT BY 1 실행
```

### 시리얼 옵션

| 옵션 | 설명 | 예시 |
|------|------|------|
| `start`       | 초기값 | `start=100` |
| `increment`   | 값 사이의 증가분 | `increment=5` |
| `minvalue`    | 최솟값 | `minvalue=1` |
| `maxvalue`    | 최댓값 | `maxvalue=999999` |
| `cycle`       | 최대/최소에 도달하면 순환 | `cycle=True` |
| `cache`       | 미리 할당할 값의 수 | `cache=20` |
| `nominvalue`  | 명시적으로 최솟값 없음 | `nominvalue=True` |
| `nomaxvalue`  | 명시적으로 최댓값 없음 | `nomaxvalue=True` |

```python
from sqlalchemy import Sequence

order_seq = Sequence(
    "order_seq",
    start=1000,
    increment=1,
    minvalue=1000,
    maxvalue=9999999,
    cycle=True,
    cache=50,
)
```

생성되는 DDL:

```sql
CREATE SERIAL order_seq START WITH 1000 INCREMENT BY 1 MINVALUE 1000 MAXVALUE 9999999 CYCLE CACHE 50
```

### 컬럼에서 시리얼 사용

```python
order_seq = Sequence("order_seq", start=1000)

orders = Table(
    "orders", metadata,
    Column("id", Integer, order_seq, primary_key=True),
    Column("description", String(200)),
)
```

컬럼 기본값은 `order_seq.NEXT_VALUE`를 호출하여 다음 시리얼 값을 가져옵니다.

### 시리얼 삭제

시리얼은 `IF EXISTS`와 함께 삭제됩니다:

```sql
DROP SERIAL IF EXISTS order_seq
```

## CREATE INDEX 및 DROP INDEX

### 기본 인덱스

```python
from sqlalchemy import Index

Index("idx_users_email", users.c.email)
```

### UNIQUE 인덱스

```python
Index("idx_users_email_unique", users.c.email, unique=True)
```

### REVERSE 인덱스

CUBRID는 내림차순 쿼리 최적화를 위한 역방향 인덱스를 지원합니다. `cubrid_reverse` dialect 옵션을 사용합니다:

```python
Index("idx_users_name_rev", users.c.name, cubrid_reverse=True)
```

!!! note
    CUBRID의 역방향 인덱스는 키를 역순으로 저장하는 B-tree 인덱스입니다. `ORDER BY column DESC`가 포함된 쿼리를 최적화합니다.

### FILTERED 인덱스 (부분 인덱스)

CUBRID는 WHERE 절이 있는 필터드 인덱스를 지원합니다. `cubrid_filtered` dialect 옵션을 사용합니다:

```python
Index(
    "idx_active_users", users.c.name,
    cubrid_filtered="email IS NOT NULL",
)
```

### FUNCTION 기반 인덱스

CUBRID는 함수 기반 인덱스를 지원합니다. `cubrid_function` dialect 옵션을 사용합니다:

```python
Index(
    "idx_users_lower_name", users.c.name,
    cubrid_function="LOWER(name)",
)
```

### 복합 인덱스

```python
Index("idx_users_name_email", users.c.name, users.c.email)
```

### 인덱스 삭제

CUBRID는 인덱스 삭제 시 테이블 이름이 필요합니다:

```sql
DROP INDEX idx_users_email ON users
```

dialect가 이를 자동으로 처리합니다.

## 테이블 코멘트

```python
users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100)),
    comment="User accounts table",
)
```

생성되는 DDL에 코멘트가 추가됩니다:

```sql
CREATE TABLE users (
    id INTEGER AUTO_INCREMENT,
    name VARCHAR(100),
    PRIMARY KEY (id)
) COMMENT='User accounts table'
```

### 테이블 코멘트 변경

```python
from sqlalchemy import inspect

# DDL을 통해
with engine.connect() as conn:
    conn.execute(text("ALTER TABLE users COMMENT='Updated comment'"))
    conn.commit()
```

## 컬럼 코멘트

```python
users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), comment="Full name of the user"),
    Column("email", String(200), comment="Primary email address"),
)
```

생성되는 DDL에 인라인 코멘트가 포함됩니다:

```sql
CREATE TABLE users (
    id INTEGER AUTO_INCREMENT,
    name VARCHAR(100) COMMENT 'Full name of the user',
    email VARCHAR(200) COMMENT 'Primary email address',
    PRIMARY KEY (id)
)
```

### 컬럼 코멘트 변경

dialect는 컬럼 코멘트 변경을 위해 `ALTER TABLE ... MODIFY ... COMMENT ...`를 생성합니다:

```sql
ALTER TABLE users MODIFY name COMMENT 'Updated column comment'
```

### 코멘트 삭제

코멘트를 빈 문자열로 설정하면 효과적으로 제거됩니다:

```sql
ALTER TABLE users COMMENT=''
ALTER TABLE users MODIFY name COMMENT ''
```
