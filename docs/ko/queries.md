# 고급 쿼리

이 페이지에서는 CUBRID 전용 쿼리 구문을 다룹니다: 계층적 쿼리 (CONNECT BY), MERGE 구문, 클릭 카운터 함수.

## 계층적 쿼리 (CONNECT BY)

CUBRID는 트리 구조 데이터를 순회하기 위한 Oracle 스타일의 계층적 쿼리를 지원합니다. `sqlalchemy_cubrid` 패키지는 이러한 쿼리를 작성하기 위한 완전한 구문 세트를 제공합니다.

### 기본 예제

자기 참조 `manager_id` 컬럼이 있는 `employees` 테이블이 주어진 경우:

```python
from sqlalchemy import Table, Column, Integer, String, MetaData

metadata = MetaData()
emp = Table(
    "employees", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100)),
    Column("manager_id", Integer),
)
```

계층 구조 쿼리:

```python
from sqlalchemy_cubrid import HierarchicalSelect, prior, level_col

stmt = HierarchicalSelect(
    emp,
    columns=[emp.c.id, emp.c.name, level_col()],
    connect_by=(prior(emp.c.id) == emp.c.manager_id),
    start_with=(emp.c.manager_id == None),
)

with engine.connect() as conn:
    result = conn.execute(stmt)
    for row in result:
        print("  " * (row[2] - 1) + row[1])
```

생성되는 SQL:

```sql
SELECT employees.id, employees.name, LEVEL
FROM employees
START WITH employees.manager_id IS NULL
CONNECT BY PRIOR employees.id = employees.manager_id
```

### HierarchicalSelect 파라미터

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `table`              | Table             | 소스 테이블 |
| `columns`            | list              | 선택할 컬럼 |
| `connect_by`         | expression        | CONNECT BY 조건 (`prior()` 포함 필수) |
| `start_with`         | expression        | 루트 행 필터 조건 |
| `where`              | expression        | 추가 WHERE 필터 (순회 전에 적용) |
| `order_siblings_by`  | list              | 각 레벨에서 형제 정렬 |
| `nocycle`            | bool              | 순환 데이터에서 무한 루프 방지 |

### prior()

계층적 관계에서 "이전" (부모) 측의 컬럼을 표시합니다:

```python
from sqlalchemy_cubrid import prior

# 부모의 id가 자식의 manager_id와 일치
connect_by = (prior(emp.c.id) == emp.c.manager_id)
```

### level_col()

계층 구조에서 깊이를 나타내는 `LEVEL` 의사 컬럼을 반환합니다 (루트는 1):

```python
from sqlalchemy_cubrid import level_col

stmt = HierarchicalSelect(
    emp,
    columns=[emp.c.name, level_col()],
    connect_by=(prior(emp.c.id) == emp.c.manager_id),
    start_with=(emp.c.manager_id == None),
)
```

### sys_connect_by_path()

루트에서 현재 노드까지의 경로 문자열을 생성합니다:

```python
from sqlalchemy_cubrid import sys_connect_by_path

stmt = HierarchicalSelect(
    emp,
    columns=[
        emp.c.name,
        sys_connect_by_path(emp.c.name, "/"),
    ],
    connect_by=(prior(emp.c.id) == emp.c.manager_id),
    start_with=(emp.c.manager_id == None),
)
```

생성되는 SQL에 포함되는 내용:

```sql
SYS_CONNECT_BY_PATH(employees.name, '/')
```

!!! note
    CUBRID는 구분자가 바인드 파라미터가 아닌 문자열 리터럴이어야 합니다. dialect가 이를 자동으로 처리합니다.

### connect_by_root()

계층 구조에서 각 행의 루트 노드 컬럼 값을 반환합니다:

```python
from sqlalchemy_cubrid import connect_by_root

stmt = HierarchicalSelect(
    emp,
    columns=[
        emp.c.name,
        connect_by_root(emp.c.name),  # 루트 직원 이름
    ],
    connect_by=(prior(emp.c.id) == emp.c.manager_id),
    start_with=(emp.c.manager_id == None),
)
```

### connect_by_isleaf()

현재 행이 리프 노드(자식이 없음)이면 1을, 그렇지 않으면 0을 반환합니다:

```python
from sqlalchemy_cubrid import connect_by_isleaf

stmt = HierarchicalSelect(
    emp,
    columns=[emp.c.name, connect_by_isleaf()],
    connect_by=(prior(emp.c.id) == emp.c.manager_id),
    start_with=(emp.c.manager_id == None),
)
```

### connect_by_iscycle()

현재 행이 순환을 유발하면 1을 반환합니다. `nocycle=True`가 필요합니다:

```python
from sqlalchemy_cubrid import connect_by_iscycle

stmt = HierarchicalSelect(
    emp,
    columns=[emp.c.name, connect_by_iscycle()],
    connect_by=(prior(emp.c.id) == emp.c.manager_id),
    start_with=(emp.c.manager_id == None),
    nocycle=True,
)
```

### NOCYCLE

데이터에 순환이 포함된 경우 무한 루프를 방지합니다:

```python
stmt = HierarchicalSelect(
    emp,
    columns=[emp.c.name, level_col()],
    connect_by=(prior(emp.c.id) == emp.c.manager_id),
    start_with=(emp.c.manager_id == None),
    nocycle=True,
)
```

생성되는 SQL:

```sql
CONNECT BY NOCYCLE PRIOR employees.id = employees.manager_id
```

### ORDER SIBLINGS BY

계층 구조의 같은 레벨에서 행을 정렬합니다:

```python
stmt = HierarchicalSelect(
    emp,
    columns=[emp.c.name, level_col()],
    connect_by=(prior(emp.c.id) == emp.c.manager_id),
    start_with=(emp.c.manager_id == None),
    order_siblings_by=[emp.c.name],
)
```

생성되는 SQL:

```sql
... ORDER SIBLINGS BY employees.name
```

### rownum()

`ROWNUM` 의사 컬럼을 반환합니다. 결과 집합에서 1부터 시작하는 순차적 행 번호를 제공합니다. 계층적 쿼리와 일반 쿼리 모두에서 사용할 수 있습니다:

```python
from sqlalchemy_cubrid import rownum

stmt = HierarchicalSelect(
    emp,
    columns=[rownum(), emp.c.name, level_col()],
    connect_by=(prior(emp.c.id) == emp.c.manager_id),
    start_with=(emp.c.manager_id == None),
)
```

생성되는 SQL:

```sql
SELECT ROWNUM, employees.name, LEVEL FROM employees ...
```

### WHERE 절

계층적 순회 전에 행을 필터링합니다:

```python
stmt = HierarchicalSelect(
    emp,
    columns=[emp.c.name, level_col()],
    connect_by=(prior(emp.c.id) == emp.c.manager_id),
    start_with=(emp.c.manager_id == None),
    where=(emp.c.name != "Intern"),
)
```

## MERGE 구문

CUBRID는 조건부 삽입/수정 (소스 테이블 또는 서브쿼리 기반 upsert)을 위한 SQL MERGE 구문을 지원합니다.

### 기본 예제

```python
from sqlalchemy_cubrid import Merge

stmt = (
    Merge(target_table)
    .using(source_table)
    .on(target_table.c.id == source_table.c.id)
    .when_matched_then_update({
        target_table.c.name: source_table.c.name,
        target_table.c.value: source_table.c.value,
    })
    .when_not_matched_then_insert({
        target_table.c.id: source_table.c.id,
        target_table.c.name: source_table.c.name,
        target_table.c.value: source_table.c.value,
    })
)

with engine.connect() as conn:
    conn.execute(stmt)
    conn.commit()
```

생성되는 SQL:

```sql
MERGE INTO target_table
USING source_table
ON (target_table.id = source_table.id)
WHEN MATCHED THEN UPDATE SET
    target_table.name = source_table.name,
    target_table.value = source_table.value
WHEN NOT MATCHED THEN INSERT (target_table.id, target_table.name, target_table.value)
    VALUES (source_table.id, source_table.name, source_table.value)
```

### Merge API

| 메서드 | 설명 |
|--------|------|
| `Merge(target)`                            | 지정된 테이블을 대상으로 MERGE 생성 |
| `.using(source)`                           | 소스 테이블 또는 서브쿼리 설정 |
| `.on(condition)`                           | 조인 조건 설정 |
| `.when_matched_then_update(dict, condition=)` | 일치하는 행에 대한 SET 절 (선택적 AND 조건) |
| `.when_matched_then_delete(condition=)`    | 일치하는 행 삭제 (선택적 AND 조건) |
| `.when_not_matched_then_insert(dict, condition=)` | 일치하지 않는 행에 대한 INSERT 절 (선택적 AND 조건) |

### WHEN MATCHED THEN DELETE

일치하는 행을 수정 대신 삭제합니다:

```python
stmt = (
    Merge(target_table)
    .using(source_table)
    .on(target_table.c.id == source_table.c.id)
    .when_matched_then_delete()
)
```

### 조건부 WHEN 절

`condition=` 파라미터를 사용하여 WHEN 절에 조건을 추가합니다:

```python
stmt = (
    Merge(target_table)
    .using(source_table)
    .on(target_table.c.id == source_table.c.id)
    .when_matched_then_update(
        {target_table.c.name: source_table.c.name},
        condition=source_table.c.active == 1,
    )
    .when_matched_then_delete(
        condition=source_table.c.active == 0,
    )
    .when_not_matched_then_insert(
        {target_table.c.id: source_table.c.id,
         target_table.c.name: source_table.c.name},
    )
)
```

생성되는 SQL:

```sql
MERGE INTO target_table USING source_table
ON (target_table.id = source_table.id)
WHEN MATCHED AND source_table.active = ? THEN UPDATE SET ...
WHEN MATCHED AND source_table.active = ? THEN DELETE
WHEN NOT MATCHED THEN INSERT (...) VALUES (...)
```

### 수정만 (삽입 없음)

```python
stmt = (
    Merge(target_table)
    .using(source_table)
    .on(target_table.c.id == source_table.c.id)
    .when_matched_then_update({
        target_table.c.name: source_table.c.name,
    })
)
```

### 삽입만 (수정 없음)

```python
stmt = (
    Merge(target_table)
    .using(source_table)
    .on(target_table.c.id == source_table.c.id)
    .when_not_matched_then_insert({
        target_table.c.id: source_table.c.id,
        target_table.c.name: source_table.c.name,
    })
)
```

## 클릭 카운터 함수

CUBRID는 `SELECT` 구문 내에서 작동하는 원자적 증가 및 감소 함수를 제공합니다. 이 함수는 CUBRID 고유 기능으로 조회수 카운터, 좋아요 수 등을 구현하는 데 사용됩니다.

### INCR()

정수 컬럼을 원자적으로 1 증가시키고 증가 **이전** 값을 반환합니다:

```python
from sqlalchemy import select
from sqlalchemy_cubrid import incr

stmt = select(incr(articles.c.view_count)).where(articles.c.id == 42)

with engine.connect() as conn:
    result = conn.execute(stmt)
    old_count = result.scalar()
    conn.commit()
```

생성되는 SQL:

```sql
SELECT INCR(articles.view_count) FROM articles WHERE articles.id = ?
```

### DECR()

정수 컬럼을 원자적으로 1 감소시키고 감소 **이전** 값을 반환합니다:

```python
from sqlalchemy_cubrid import decr

stmt = select(decr(articles.c.view_count)).where(articles.c.id == 42)
```

### 클릭 카운터 제약 사항

!!! warning
    - 클릭 카운터는 `SMALLINT`, `INT`, `BIGINT` 컬럼에서만 작동합니다.
    - 결과 집합은 **정확히 한 행**을 포함해야 합니다.
    - 클릭 카운터는 SELECT와 UPDATE를 단일 원자적 작업으로 결합합니다.

## 내장 함수

dialect는 올바른 타입 추론을 위해 CUBRID 전용 내장 함수를 `GenericFunction` 클래스로 등록합니다:

### NVL / IFNULL

```python
from sqlalchemy import func, select

# NVL(expr, default) -- expr이 NULL이면 default 반환
stmt = select(func.nvl(users.c.nickname, users.c.name))

# IFNULL(expr, default) -- NVL의 별칭
stmt = select(func.ifnull(users.c.nickname, "익명"))
```

### NVL2

```python
# NVL2(expr, not_null_val, null_val)
stmt = select(func.nvl2(users.c.email, "이메일 있음", "이메일 없음"))
```

### DECODE

```python
# DECODE(expr, search1, result1, ..., default)
stmt = select(func.decode(users.c.status, 1, "활성", 2, "비활성", "알 수 없음"))
```

### IF

```python
# IF(condition, true_val, false_val)
stmt = select(func.if_(users.c.age >= 18, "성인", "미성년"))
```

### GROUP_CONCAT

```python
# GROUP_CONCAT(expr) -- 그룹 내 값을 연결
stmt = select(func.group_concat(users.c.name)).group_by(users.c.department)
```

## 임포트 참조

모든 쿼리 구문은 최상위 패키지에서 사용할 수 있습니다:

```python
from sqlalchemy_cubrid import (
    # 계층적 쿼리
    HierarchicalSelect,
    prior,
    level_col,
    sys_connect_by_path,
    connect_by_root,
    connect_by_isleaf,
    connect_by_iscycle,
    rownum,
    # MERGE
    Merge,
    # 클릭 카운터
    incr,
    decr,
    # 내장 함수
    group_concat,
    nvl,
    nvl2,
    decode,
    if_,
    ifnull,
)
```
