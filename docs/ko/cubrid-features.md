# CUBRID 고유 기능

이 페이지에서는 객체-관계형 데이터베이스인 CUBRID의 고유 기능을 다룹니다: 컬렉션 타입, 클래스 상속, OID (Object Identifier) 참조.

## 컬렉션 타입

CUBRID는 단일 컬럼에 여러 값을 저장하기 위한 세 가지 컬렉션 타입을 제공합니다. `sqlalchemy_cubrid.types` 모듈은 각각에 대한 사용자 정의 SQLAlchemy 타입을 제공합니다.

### CubridSet

중복이 없는 비순서 컬렉션입니다. Python 값은 `set`으로 반환됩니다.

```python
from sqlalchemy import Table, Column, Integer, MetaData
from sqlalchemy_cubrid.types import CubridSet

metadata = MetaData()

products = Table(
    "products", metadata,
    Column("id", Integer, primary_key=True),
    Column("tags", CubridSet("VARCHAR(50)")),
)
```

생성되는 DDL:

```sql
CREATE TABLE products (
    id INTEGER AUTO_INCREMENT,
    tags SET_OF(VARCHAR(50)),
    PRIMARY KEY (id)
)
```

삽입 및 조회:

```python
with engine.connect() as conn:
    conn.execute(
        products.insert().values(id=1, tags={"python", "database", "orm"})
    )
    conn.commit()

    row = conn.execute(products.select().where(products.c.id == 1)).first()
    print(row.tags)       # {'python', 'database', 'orm'}
    print(type(row.tags)) # <class 'set'>
```

### CubridMultiset

중복을 허용하는 비순서 컬렉션입니다. Python 값은 `list`로 반환됩니다.

```python
from sqlalchemy_cubrid.types import CubridMultiset

scores = Table(
    "scores", metadata,
    Column("id", Integer, primary_key=True),
    Column("values", CubridMultiset("INTEGER")),
)
```

생성되는 DDL:

```sql
values MULTISET_OF(INTEGER)
```

### CubridList

중복을 허용하는 순서 있는 컬렉션입니다 (CUBRID에서 SEQUENCE라고도 합니다). Python 값은 `list`로 반환됩니다.

```python
from sqlalchemy_cubrid.types import CubridList

history = Table(
    "history", metadata,
    Column("id", Integer, primary_key=True),
    Column("events", CubridList("VARCHAR(200)")),
)
```

생성되는 DDL:

```sql
events SEQUENCE_OF(VARCHAR(200))
```

!!! note
    CUBRID는 내부적으로 `SEQUENCE_OF` DDL 구문을 사용합니다. `LIST`와 `SEQUENCE`는 CUBRID에서 동의어입니다. CUBRID가 `LIST_OF` 구문을 지원하지 않으므로 dialect는 DDL 생성 시 `SEQUENCE_OF`를 사용합니다.

### 요소 타입 파라미터

요소 타입은 CUBRID DDL 구문에 맞는 문자열로 전달됩니다:

```python
CubridSet("VARCHAR(100)")
CubridSet("INTEGER")
CubridSet("DOUBLE")
CubridMultiset("VARCHAR(1073741823)")  # STRING 동등
CubridList("NUMERIC(10,2)")
```

요소 타입을 지정하지 않으면 기본값은 `VARCHAR(1073741823)`입니다.

### 바이너리 포맷 파싱

pycubrid는 컬렉션 값을 원시 바이너리 포맷으로 반환합니다. dialect에는 와이어 포맷을 디코딩하는 자동 파서 (`_parse_collection_bytes`)가 포함되어 있습니다:

- 4바이트: 타입 식별자 (리틀 엔디안)
- 4바이트: 요소 수 (리틀 엔디안)
- 요소별: 1바이트 크기 + 데이터 바이트 + 3바이트 패딩 (마지막 요소는 패딩 없음)

이 파싱은 각 컬렉션 타입의 `result_processor`에서 투명하게 처리됩니다.

## 클래스 상속 (UNDER)

CUBRID는 클래스 상속을 지원하는 객체-관계형 데이터베이스입니다. `UNDER`로 생성된 자식 테이블은 부모 테이블의 모든 컬럼을 상속받습니다.

### 상속 테이블 생성

```python
from sqlalchemy_cubrid import CreateTableUnder

# 먼저 부모 테이블을 일반적으로 생성
parent = Table(
    "person", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100)),
)
metadata.create_all(engine)

# 그런 다음 person을 상속받는 자식 테이블 생성
child_ddl = CreateTableUnder(
    "student",       # 자식 테이블 이름
    "person",        # 부모 테이블 이름
    Column("grade", Integer),
    Column("school", String(100)),
)

with engine.connect() as conn:
    conn.execute(child_ddl)
    conn.commit()
```

생성되는 DDL:

```sql
CREATE TABLE student UNDER person (
    grade INTEGER,
    school VARCHAR(100)
)
```

`student` 테이블은 `person`에서 상속받은 `id`와 `name` 컬럼을 자동으로 갖게 되며, 자체적으로 `grade`와 `school` 컬럼이 추가됩니다.

### 상속 테이블 삭제

```python
from sqlalchemy_cubrid import DropTableInheritance

drop_ddl = DropTableInheritance("student")

with engine.connect() as conn:
    conn.execute(drop_ddl)
    conn.commit()
```

생성되는 DDL:

```sql
DROP TABLE IF EXISTS student
```

### 상속 메타데이터 조회

#### get_super_class()

부모 클래스 이름을 반환하며, 부모가 없으면 `None`을 반환합니다:

```python
from sqlalchemy_cubrid import get_super_class

with engine.connect() as conn:
    parent = get_super_class(conn, "student")
    print(parent)  # "person"

    parent = get_super_class(conn, "person")
    print(parent)  # None
```

#### get_sub_classes()

직접 자식 클래스 이름 목록을 반환합니다:

```python
from sqlalchemy_cubrid import get_sub_classes

with engine.connect() as conn:
    children = get_sub_classes(conn, "person")
    print(children)  # ["student"]
```

#### get_inherited_columns()

상속 출처 정보와 함께 컬럼 정보를 반환합니다:

```python
from sqlalchemy_cubrid import get_inherited_columns

with engine.connect() as conn:
    columns = get_inherited_columns(conn, "student")
    for col in columns:
        print(col)
    # {"name": "id", "from_class": "person", "def_order": 0}
    # {"name": "name", "from_class": "person", "def_order": 1}
    # {"name": "grade", "from_class": None, "def_order": 2}
    # {"name": "school", "from_class": None, "def_order": 3}
```

`from_class=None`인 컬럼은 로컬 (자식 테이블에 직접 정의된) 컬럼입니다. `from_class` 값이 있는 컬럼은 해당 부모 클래스에서 상속받은 것입니다.

### Inspector 통합

dialect는 Inspector 객체에서도 이러한 메서드를 제공합니다:

```python
from sqlalchemy import inspect

insp = inspect(engine)

# 부모 클래스 이름 가져오기
parent = insp.dialect.get_super_class_name(conn, "student")

# 자식 클래스 이름 가져오기
children = insp.dialect.get_sub_class_names(conn, "person")
```

## OID 참조

CUBRID에서 모든 행은 OID (Object Identifier)를 가집니다. 컬럼은 클래스 이름을 컬럼 타입으로 사용하여 다른 클래스를 참조할 수 있으며, 참조되는 클래스의 인스턴스에 대한 OID 참조를 저장합니다.

### CubridOID 타입

`CubridOID` 타입은 OID 참조 컬럼을 나타냅니다:

```python
from sqlalchemy_cubrid import CubridOID

department = Table(
    "department", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100)),
    Column("manager", CubridOID("person")),
)
```

생성되는 DDL:

```sql
CREATE TABLE department (
    id INTEGER AUTO_INCREMENT,
    name VARCHAR(100),
    manager person,
    PRIMARY KEY (id)
)
```

`manager` 컬럼은 `person` 테이블의 행에 대한 OID 참조를 저장합니다.

!!! warning
    `DONT_REUSE_OID`로 생성된 테이블만 OID 컬럼으로 참조할 수 있습니다. CUBRID 10.x부터 기본값이 `REUSE_OID`이므로 참조되는 테이블에 `DONT_REUSE_OID`를 명시적으로 설정해야 합니다. 단, `DONT_REUSE_OID` 키워드는 **CUBRID 11.0 이상**에서만 지원되며, 10.2에서는 사용할 수 없습니다. dialect는 11.0 미만 버전에서 자동으로 이 키워드를 생략합니다.

### CreateTableDontReuseOID

OID로 참조 가능한 테이블을 생성하기 위한 DDL 구문:

```python
from sqlalchemy_cubrid import CreateTableDontReuseOID
from sqlalchemy import Column, Integer, String

ddl = CreateTableDontReuseOID(
    "person",
    Column("id", Integer, primary_key=True),
    Column("name", String(50)),
)

with engine.connect() as conn:
    conn.execute(ddl)
    conn.commit()
```

생성되는 DDL:

```sql
CREATE TABLE person (id INTEGER, name VARCHAR(50)) DONT_REUSE_OID
```

테이블 dialect 옵션을 사용할 수도 있습니다:

```python
person = Table(
    "person", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(50)),
    cubrid_dont_reuse_oid=True,
)
```

### deref() -- 경로 표현식

CUBRID는 점 표기법 (경로 표현식)을 사용하여 OID 참조를 탐색할 수 있습니다. `deref()` 함수가 이러한 표현식을 생성합니다:

```python
from sqlalchemy_cubrid import deref
from sqlalchemy import select, literal_column, text

# 단일 수준 역참조
# SQL: SELECT manager.name FROM department
stmt = select(
    deref(literal_column("manager"), "name")
).select_from(text("department"))

with engine.connect() as conn:
    result = conn.execute(stmt)
    for row in result:
        print(row[0])  # 매니저의 이름
```

### 연쇄 역참조

다중 수준 OID 참조의 경우 `deref()` 호출을 연쇄합니다:

```python
# department.manager -> person이고, person.address -> address_table인 경우
# SQL: SELECT manager.address.city FROM department
stmt = select(
    deref(deref(literal_column("manager"), "address"), "city")
).select_from(text("department"))
```

이는 다음과 같이 컴파일됩니다:

```sql
SELECT manager.address.city FROM department
```

### 사용자 정의 결과 타입

기본적으로 `deref()`는 `String`을 반환합니다. 올바른 Python 변환을 위해 타입을 지정합니다:

```python
from sqlalchemy import Integer

# 매니저의 ID (정수) 가져오기
stmt = select(
    deref(literal_column("manager"), "id", type_=Integer())
).select_from(text("department"))
```

### OID 컬럼 검사

dialect의 `get_oid_columns()`를 사용하여 OID 참조 컬럼을 조회합니다:

```python
from sqlalchemy import inspect

insp = inspect(engine)

with engine.connect() as conn:
    oid_cols = insp.dialect.get_oid_columns(conn, "department")
    for col in oid_cols:
        print(col)
    # {"name": "manager", "referenced_class": "person"}
```

## 파티셔닝

CUBRID는 RANGE, HASH, LIST 파티셔닝을 지원합니다. dialect는 기존 테이블을 파티셔닝하기 위한 DDL construct를 제공합니다.

### RANGE 파티셔닝

```python
from sqlalchemy_cubrid import PartitionByRange, RangePartition

ddl = PartitionByRange("orders", "order_date", [
    RangePartition("p2024", "'2025-01-01'"),
    RangePartition("p2025", "'2026-01-01'"),
    RangePartition("pmax", "MAXVALUE"),
])

with engine.connect() as conn:
    conn.execute(ddl)
    conn.commit()
```

생성되는 SQL:

```sql
ALTER TABLE "orders" PARTITION BY RANGE ("order_date") (
    PARTITION "p2024" VALUES LESS THAN ('2025-01-01'),
    PARTITION "p2025" VALUES LESS THAN ('2026-01-01'),
    PARTITION "pmax" VALUES LESS THAN (MAXVALUE)
)
```

### HASH 파티셔닝

```python
from sqlalchemy_cubrid import PartitionByHash

ddl = PartitionByHash("orders", "id", 4)

with engine.connect() as conn:
    conn.execute(ddl)
    conn.commit()
```

생성되는 SQL:

```sql
ALTER TABLE "orders" PARTITION BY HASH ("id") PARTITIONS 4
```

### LIST 파티셔닝

```python
from sqlalchemy_cubrid import PartitionByList, ListPartition

ddl = PartitionByList("orders", "region", [
    ListPartition("p_east", ["'east'", "'northeast'"]),
    ListPartition("p_west", ["'west'", "'southwest'"]),
])

with engine.connect() as conn:
    conn.execute(ddl)
    conn.commit()
```

생성되는 SQL:

```sql
ALTER TABLE "orders" PARTITION BY LIST ("region") (
    PARTITION "p_east" VALUES IN ('east', 'northeast'),
    PARTITION "p_west" VALUES IN ('west', 'southwest')
)
```

## DBLINK (11.2+)

CUBRID 11.2에서 원격 CUBRID 데이터베이스를 조회하는 DBLINK가 도입되었습니다.

### 원격 서버 생성

```python
from sqlalchemy_cubrid import CreateServer, DropServer

ddl = CreateServer(
    "remote_srv",
    host="192.168.1.10",
    port=33000,
    dbname="demodb",
    user="dba",
    password="",
)

with engine.connect() as conn:
    conn.execute(ddl)
    conn.commit()
```

생성되는 SQL:

```sql
CREATE SERVER "remote_srv" (
    HOST='192.168.1.10', PORT=33000, DBNAME='demodb', USER='dba', PASSWORD=''
)
```

### 서버 삭제

```python
from sqlalchemy_cubrid import DropServer

with engine.connect() as conn:
    conn.execute(DropServer("remote_srv"))
    conn.commit()
```

### 쿼리에서 DBLINK 사용

`DbLink` 헬퍼는 `text()`와 함께 사용할 수 있는 FROM절 프래그먼트를 생성합니다:

```python
from sqlalchemy_cubrid import DbLink
from sqlalchemy import text

link = DbLink(
    "remote_srv",
    "SELECT id, name FROM employees",
    columns=[("id", "INT"), ("name", "VARCHAR(100)")],
)

with engine.connect() as conn:
    result = conn.execute(text(
        f"SELECT * FROM {link.as_text('t')}"
    ))
```

생성되는 SQL:

```sql
SELECT * FROM DBLINK(remote_srv, 'SELECT id, name FROM employees')
    AS t(id INT, name VARCHAR(100))
```

!!! note
    DBLINK는 CUBRID 11.2 이상이 필요합니다. 원격 데이터베이스도 CUBRID 인스턴스여야 합니다.

## 임포트 참조

```python
# 컬렉션 타입
from sqlalchemy_cubrid.types import CubridSet, CubridMultiset, CubridList

# 상속
from sqlalchemy_cubrid import (
    CreateTableUnder,
    DropTableInheritance,
    get_super_class,
    get_sub_classes,
    get_inherited_columns,
)

# OID 참조
from sqlalchemy_cubrid import (
    CubridOID,
    deref,
    CreateTableDontReuseOID,
)

# 파티셔닝
from sqlalchemy_cubrid import (
    PartitionByRange,
    PartitionByHash,
    PartitionByList,
    RangePartition,
    HashPartition,
    ListPartition,
)

# DBLINK (11.2+)
from sqlalchemy_cubrid import CreateServer, DropServer, DbLink
```
