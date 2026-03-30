# 인트로스펙션

이 페이지에서는 CUBRID 데이터베이스 객체를 리플렉션하는 데 사용할 수 있는 Inspector 메서드를 설명합니다. 모든 리플렉션 메서드는 성능을 위해 `@reflection.cache`를 사용합니다.

## 개요

CUBRID dialect는 런타임에 데이터베이스 구조를 파악할 수 있는 포괄적인 인트로스펙션 메서드 세트를 제공합니다. 이러한 메서드는 SQLAlchemy의 `inspect()` 인터페이스를 통해 또는 dialect에서 직접 접근할 수 있습니다.

```python
from sqlalchemy import inspect, create_engine

engine = create_engine("cubrid://dba:@localhost:33000/testdb")
insp = inspect(engine)
```

## 테이블 메서드

### get_table_names()

모든 사용자 테이블 이름 목록을 반환합니다 (시스템 테이블과 뷰 제외):

```python
tables = insp.get_table_names()
# ['employees', 'departments', 'orders', ...]
```

사용되는 쿼리:

```sql
SELECT class_name FROM db_class
WHERE is_system_class = 'NO' AND class_type = 'CLASS'
ORDER BY class_name
```

### has_table()

특정 테이블이 존재하는지 확인합니다:

```python
exists = insp.has_table("employees")  # True 또는 False
```

!!! note
    CUBRID는 모든 식별자를 소문자로 변환합니다. 확인은 소문자로 변환된 이름에 대해 수행됩니다.

## 컬럼 메서드

### get_columns()

테이블의 컬럼 정보를 반환합니다. 각 컬럼은 다음 키를 가진 딕셔너리입니다:

| 키 | 타입 | 설명 |
|----|------|------|
| `name`            | str      | 컬럼 이름 |
| `type`            | TypeObj  | SQLAlchemy 타입 인스턴스 |
| `nullable`        | bool     | NULL 허용 여부 |
| `default`         | str/None | 기본값 표현식 |
| `autoincrement`   | bool     | AUTO_INCREMENT 설정 여부 |
| `comment`         | str/None | 컬럼 코멘트 |

```python
columns = insp.get_columns("employees")
for col in columns:
    print(f"{col['name']}: {col['type']} "
          f"{'NULL' if col['nullable'] else 'NOT NULL'}")
    # id: INTEGER NOT NULL
    # name: VARCHAR(100) NULL
    # salary: NUMERIC(10, 2) NULL
```

컬럼 코멘트는 `db_attribute` 카탈로그 테이블에서 별도로 가져옵니다.

!!! note
    CUBRID의 `SHOW COLUMNS`는 `SMALLINT` 대신 `SHORT`로, `INT` 대신 `INTEGER`로 보고합니다. dialect는 타입 파싱 시 이를 정규화합니다.

## 제약 조건 메서드

### get_pk_constraint()

기본 키 제약 조건을 반환합니다:

```python
pk = insp.get_pk_constraint("employees")
print(pk)
# {'constrained_columns': ['id'], 'name': 'pk_employees_id'}
```

### get_foreign_keys()

외래 키 제약 조건을 반환합니다. CUBRID는 카탈로그 뷰에서 FK 참조 정보를 노출하지 않으므로 dialect는 `SHOW CREATE TABLE` 출력을 파싱합니다:

```python
fks = insp.get_foreign_keys("orders")
for fk in fks:
    print(fk)
# {
#     'name': 'fk_orders_customer',
#     'constrained_columns': ['customer_id'],
#     'referred_schema': None,
#     'referred_table': 'customers',
#     'referred_columns': ['id'],
#     'options': {
#         'ondelete': 'CASCADE',
#         'onupdate': 'NO ACTION',
#     },
# }
```

!!! note
    `options` 딕셔너리에는 참조 무결성 액션이 포함됩니다. CUBRID가 지원하는 액션은 `CASCADE`, `SET NULL`, `NO ACTION`, `RESTRICT`입니다. DDL에서 명시적으로 지정하지 않은 경우 CUBRID의 기본값은 `RESTRICT`입니다.

!!! note
    뷰의 경우 `SHOW CREATE TABLE`이 실패합니다. dialect는 이를 감지하고 뷰에는 외래 키가 없으므로 빈 목록을 반환합니다.

### get_unique_constraints()

유니크 제약 조건을 반환합니다 (기본 키와 외래 키 제외):

```python
uqs = insp.get_unique_constraints("employees")
for uq in uqs:
    print(uq)
# {
#     'name': 'uq_employees_email',
#     'column_names': ['email'],
#     'duplicates_index': 'uq_employees_email',
# }
```

### get_check_constraints()

CUBRID는 CHECK 제약 조건을 파싱하지만 적용하거나 저장**하지 않습니다**. 이 메서드는 항상 빈 목록을 반환합니다:

```python
checks = insp.get_check_constraints("employees")
print(checks)  # []
```

!!! warning
    DDL에서 CHECK 제약 조건을 정의하더라도 CUBRID는 구문을 받아들이지만 제약 조건을 자동으로 무시합니다. CHECK 제약 조건을 위한 카탈로그 테이블이 없습니다.

## 인덱스 메서드

### get_indexes()

CUBRID 전용 dialect 옵션을 포함한 인덱스 정보를 반환합니다:

```python
indexes = insp.get_indexes("employees")
for idx in indexes:
    print(idx)
```

각 인덱스 딕셔너리에는 다음이 포함됩니다:

| 키 | 타입 | 설명 |
|----|------|------|
| `name`            | str       | 인덱스 이름 |
| `unique`          | bool      | 유니크 인덱스 여부 |
| `column_names`    | list[str] | 인덱싱된 컬럼 이름 |
| `column_sorting`  | dict      | 컬럼 정렬 방향 (ASC가 아닌 경우) |
| `dialect_options` | dict      | CUBRID 전용 옵션 (아래 참조) |

#### get_indexes()의 dialect 옵션

| 키 | 타입 | 설명 |
|----|------|------|
| `cubrid_reverse`   | bool     | 역방향 인덱스인 경우 True |
| `cubrid_filtered`  | str      | 필터드 인덱스의 필터 표현식 |
| `cubrid_function`  | str      | 함수 기반 인덱스의 함수 표현식 |

```python
indexes = insp.get_indexes("employees")
for idx in indexes:
    if idx["dialect_options"].get("cubrid_reverse"):
        print(f"{idx['name']}은(는) 역방향 인덱스입니다")
    if "cubrid_filtered" in idx["dialect_options"]:
        print(f"{idx['name']} 필터: {idx['dialect_options']['cubrid_filtered']}")
    if "cubrid_function" in idx["dialect_options"]:
        print(f"{idx['name']} 함수: {idx['dialect_options']['cubrid_function']}")
```

### has_index()

테이블에 특정 인덱스가 존재하는지 확인합니다:

```python
from sqlalchemy import inspect

insp = inspect(engine)

# has_index는 dialect를 통해 사용할 수 있습니다
with engine.connect() as conn:
    exists = engine.dialect.has_index(conn, "employees", "idx_emp_name")
```

## 뷰 메서드

### get_view_names()

모든 사용자 정의 뷰 이름을 반환합니다:

```python
views = insp.get_view_names()
# ['active_employees', 'department_summary', ...]
```

### get_view_definition()

뷰의 SQL 정의를 반환합니다:

```python
definition = insp.get_view_definition("active_employees")
print(definition)
# "SELECT id, name, email FROM employees WHERE active = 1"
```

## 시퀀스 메서드

### get_sequence_names()

사용자가 생성한 시리얼 이름을 반환합니다. AUTO_INCREMENT 컬럼을 위해 자동 생성된 시리얼은 제외됩니다:

```python
sequences = insp.get_sequence_names()
# ['order_seq', 'invoice_seq']
```

!!! note
    `db_serial` 카탈로그 테이블의 속성 참조 컬럼이 CUBRID 11.4에서 `att_name`에서 `attr_name`으로 변경되었습니다. dialect가 이를 투명하게 처리합니다.

### has_sequence()

특정 시리얼이 존재하는지 확인합니다:

```python
exists = insp.has_sequence("order_seq")  # True 또는 False
```

## 코멘트 메서드

### get_table_comment()

테이블 코멘트를 반환합니다:

```python
comment = insp.get_table_comment("employees")
print(comment)
# {'text': 'Employee records table'}
# 또는 코멘트가 설정되지 않은 경우 {'text': None}
```

## 상속 메서드

이 메서드들은 Inspector 객체가 아닌 dialect 객체에서 사용할 수 있습니다.

### get_super_class_name()

테이블이 UNDER 상속을 사용하는 경우 부모 클래스 이름을 반환합니다:

```python
with engine.connect() as conn:
    parent = engine.dialect.get_super_class_name(conn, "student")
    print(parent)  # "person" 또는 None
```

### get_sub_class_names()

직접 자식 클래스 이름을 반환합니다:

```python
with engine.connect() as conn:
    children = engine.dialect.get_sub_class_names(conn, "person")
    print(children)  # ["student", "employee"]
```

## OID 참조 메서드

### get_oid_columns()

테이블의 OID 참조 컬럼을 반환합니다:

```python
with engine.connect() as conn:
    oid_cols = engine.dialect.get_oid_columns(conn, "department")
    for col in oid_cols:
        print(col)
    # {"name": "manager", "referenced_class": "person"}
    # {"name": "location", "referenced_class": "address"}
```

각 항목에는 다음이 포함됩니다:

| 키 | 타입 | 설명 |
|----|------|------|
| `name`              | str  | 컬럼 이름 |
| `referenced_class`  | str  | OID가 가리키는 CUBRID 클래스 |

## 캐싱

모든 리플렉션 메서드는 `@reflection.cache`로 데코레이트되어 있으며, 이는 다음을 의미합니다:

- 결과는 `info_cache` 딕셔너리를 사용하여 연결별로 캐싱됩니다
- 동일한 인자로 이후 호출 시 데이터베이스를 조회하지 않고 캐싱된 결과를 반환합니다
- 캐시는 Inspector 인스턴스 (및 기본 연결)에 범위가 지정됩니다

```python
# 이 두 호출은 데이터베이스를 한 번만 조회합니다:
tables1 = insp.get_table_names()
tables2 = insp.get_table_names()  # 캐싱된 결과 반환
```

## 내부 헬퍼

### _has_object()

테이블이나 뷰가 존재하는지 확인합니다 (객체 존재가 필요한 작업 전에 내부적으로 사용):

```python
# 내부적으로 사용, 공개 API의 일부가 아님
# 객체가 존재하지 않으면 NoSuchTableError를 발생시킴
```

### _is_view()

이름이 뷰를 참조하는지 확인합니다 (CUBRID 용어로 VCLASS):

```python
# 뷰별 동작을 처리하기 위해 내부적으로 사용
# (예: 뷰에는 외래 키가 없음)
```

### _resolve_type()

`SHOW COLUMNS`의 CUBRID 타입 문자열을 SQLAlchemy 타입 인스턴스로 파싱합니다:

```python
# 내부: "VARCHAR(100)" -> VARCHAR(100)
# 내부: "NUMERIC(15,2)" -> NUMERIC(15, 2)
# 내부: "ENUM('a','b','c')" -> Enum('a', 'b', 'c')
# 내부: "SET_OF(INTEGER)" -> CubridSet(INTEGER)
# 내부: "MULTISET_OF(VARCHAR(255))" -> CubridMultiset(VARCHAR(255))
# 내부: "SEQUENCE_OF(DOUBLE)" -> CubridList(DOUBLE)
```

!!! note
    컬렉션 타입(`SET_OF`, `MULTISET_OF`, `SEQUENCE_OF`)은 리플렉션 시 각각 `CubridSet`, `CubridMultiset`, `CubridList` 타입 인스턴스로 올바르게 변환됩니다. 내부 요소 타입도 함께 파싱되어 보존됩니다.
