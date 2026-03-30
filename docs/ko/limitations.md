# 알려진 제한 사항

이 페이지에서는 CUBRID dialect의 알려진 제한 사항, 다른 데이터베이스와의 차이점, SQLAlchemy 테스트 스위트 결과를 설명합니다.

## 식별자 처리

### 모든 식별자는 소문자로 변환됩니다

CUBRID는 인용되지 않은 모든 식별자를 소문자로 정규화합니다. 테이블 및 컬럼 이름은 어떻게 지정하든 소문자로 저장됩니다:

```python
# 이 모든 것이 같은 테이블을 생성합니다:
Table("MyTable", metadata, ...)
Table("MYTABLE", metadata, ...)
Table("mytable", metadata, ...)
# 모두 mytable로 저장
```

!!! note
    dialect는 CUBRID의 SQL 표준 인용에 맞춰 큰따옴표 (`"`)를 식별자 인용 문자로 사용합니다. 그러나 인용된 식별자도 CUBRID 서버 설정에 따라 소문자로 변환될 수 있습니다.

## 날짜/시간 정밀도

### DATETIME은 밀리초 정밀도입니다

CUBRID DATETIME은 날짜와 시간을 **밀리초** (3자리) 정밀도로 저장하며, MySQL이나 PostgreSQL의 마이크로초 (6자리) 정밀도가 아닙니다:

```
CUBRID:     2026-03-29 12:34:56.789       (3자리)
MySQL:      2026-03-29 12:34:56.789123    (6자리)
PostgreSQL: 2026-03-29 12:34:56.789123    (6자리)
```

Python datetime 객체에 마이크로초 값이 있으면 밀리초 미만 부분이 저장 시 잘립니다.

```python
import datetime

# Python: microseconds = 789123
dt = datetime.datetime(2026, 3, 29, 12, 34, 56, 789123)

# CUBRID에서 저장 및 조회 후: microseconds = 789000
# 마지막 3자리 (123)가 손실됩니다
```

## AUTO_INCREMENT 제한 사항

### 자동 UNIQUE 인덱스 없음

MySQL과 달리 CUBRID의 AUTO_INCREMENT는 해당 컬럼에 UNIQUE 인덱스를 **자동으로 생성하지 않습니다**. 유일성이 필요한 경우 (보통 기본 키의 경우 필요) PRIMARY KEY 또는 UNIQUE 제약 조건을 명시적으로 정의해야 합니다.

```python
# 올바른 방법: PRIMARY KEY가 유일성을 보장
Column("id", Integer, primary_key=True, autoincrement=True)

# PRIMARY KEY 없이 AUTO_INCREMENT만으로는 유일성이 보장되지 않음
```

### 테이블당 하나만

CUBRID는 테이블당 AUTO_INCREMENT 컬럼을 하나만 허용합니다. 여러 AUTO_INCREMENT 컬럼을 정의하려고 하면 오류가 발생합니다.

## CHECK 제약 조건

### 적용되지 않음

CUBRID는 DDL에서 CHECK 제약 조건을 파싱하지만 런타임에 **적용하지 않습니다**. CHECK 제약 조건을 위반하는 데이터도 오류 없이 허용됩니다:

```sql
CREATE TABLE test (
    age INTEGER CHECK (age >= 0)
);

-- CHECK를 위반하지만 성공합니다:
INSERT INTO test (age) VALUES (-5);
```

CUBRID가 카탈로그에 CHECK 제약 조건을 저장하지 않으므로 dialect의 `get_check_constraints()`는 항상 빈 목록을 반환합니다.

## 누락된 SQL 기능

### BOOLEAN 타입 없음

CUBRID에는 네이티브 BOOLEAN 컬럼 타입이 없습니다. dialect는 `Boolean`을 `SMALLINT`로 매핑합니다:

- `True`는 `1`로 저장
- `False`는 `0`으로 저장

### RETURNING 절 없음

CUBRID는 `INSERT ... RETURNING`, `UPDATE ... RETURNING`, `DELETE ... RETURNING`을 지원하지 않습니다. dialect는 다음을 명시적으로 설정합니다:

```python
insert_returning = False
update_returning = False
delete_returning = False
```

마지막으로 삽입된 ID는 `cursor.lastrowid`를 통해 얻습니다.

### 임시 테이블 없음

CUBRID는 `CREATE TEMPORARY TABLE` 또는 `CREATE TEMP TABLE`을 지원하지 않습니다. 임시 저장소가 필요한 경우 세션별 이름 규칙을 사용한 일반 테이블을 사용하고 이후에 정리하는 것을 고려하십시오.

### RELEASE SAVEPOINT 없음

CUBRID는 `SAVEPOINT`와 `ROLLBACK TO SAVEPOINT`를 지원하지만 `RELEASE SAVEPOINT`는 지원**하지 않습니다**. dialect는 릴리스 작업을 자동으로 건너뜁니다:

```python
def do_release_savepoint(self, connection, name):
    # CUBRID does not support RELEASE SAVEPOINT -- silently skip
    pass
```

이를 통해 SQLAlchemy의 중첩 트랜잭션 (savepoint) 지원이 올바르게 작동합니다.

### FOR SHARE 없음

CUBRID는 `FOR SHARE` 또는 `LOCK IN SHARE MODE`를 지원하지 않습니다. `with_for_update(read=True)` 사용 시 dialect가 해당 절을 자동으로 생략합니다.

### NCHAR / NCHAR VARYING 없음

`NCHAR`과 `NCHAR VARYING`은 CUBRID 9.0에서 제거되었습니다. dialect는 다음과 같이 매핑합니다:

- `NCHAR(n)` -> `CHAR(n)`
- `NVARCHAR(n)` -> `VARCHAR(n)`

### FLOAT 정밀도 승격

`FLOAT(p)`에서 `p > 7`로 지정하면 CUBRID가 자동으로 타입을 `DOUBLE`로 승격합니다. dialect는 타입 컴파일러에서 이 동작을 반영합니다.

### 집합 연산은 CUBRID 키워드를 사용합니다

CUBRID는 `EXCEPT` 대신 `DIFFERENCE`를, `INTERSECT` 대신 `INTERSECTION`을 사용합니다:

| SQL 표준 | CUBRID |
|----------|--------|
| `EXCEPT`       | `DIFFERENCE`      |
| `EXCEPT ALL`   | `DIFFERENCE ALL`  |
| `INTERSECT`    | `INTERSECTION`    |
| `INTERSECT ALL`| `INTERSECTION ALL`|

dialect가 컴파일러에서 이를 자동으로 처리합니다.

### DDL은 비트랜잭션입니다

CUBRID는 모든 DDL 구문을 자동 커밋합니다. 트랜잭션 내에서 `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`을 롤백할 수 없습니다.

## SQLAlchemy 테스트 스위트 결과

dialect는 SQLAlchemy 표준 dialect 테스트 스위트에 대해 다음 결과로 테스트되었습니다:

| 카테고리 | 수 |
|----------|-----|
| 통과   | 736   |
| 실패   | 19    |
| 건너뜀 | 878   |
| 오류   | 22    |

### 실패 카테고리

19개의 테스트 실패는 다음 카테고리에 해당합니다:

#### 식별자 소문자화 (8건)

`quoted_name` 관련 PK, FK, Index, Unique constraint 테스트입니다. CUBRID는 인용된 식별자도 소문자로 변환하므로 대소문자가 보존된 제약 조건 이름을 기대하는 테스트가 실패합니다.

#### FK 파싱 괄호 컬럼명 (6건)

`BizarroCharacterTest`의 `col(3)` 형식과 같이 괄호를 포함하는 컬럼명이 외래 키 파싱 시 올바르게 처리되지 않는 테스트입니다.

#### CTE INSERT 미지원 (1건)

CUBRID가 CTE(Common Table Expression)를 사용한 INSERT 구문을 지원하지 않아 발생하는 실패입니다.

#### ROWS BETWEEN 바인드 파라미터 (1건)

윈도우 함수의 `ROWS BETWEEN` 절에서 바인드 파라미터를 사용할 수 없어 발생하는 실패입니다.

#### JSON 공백 정규화 (1건)

CUBRID가 JSON 값을 저장할 때 공백을 정규화하므로 원본 JSON 문자열과 정확히 일치하는 결과를 기대하는 테스트가 실패합니다.

#### ENUM non-ASCII (1건)

ENUM 값에 non-ASCII 문자 (예: 한글, 일본어 등)를 사용할 때 발생하는 호환성 문제입니다.

#### 격리 수준 리셋 (1건)

트랜잭션 격리 수준을 기본값으로 리셋하는 동작이 기대대로 작동하지 않아 발생하는 실패입니다.

### 오류 카테고리 (22건)

22개의 오류는 주로 다음 원인에 의해 발생합니다:

- **연결/드라이버 문제 (10건):** 특정 파라미터 바인딩 패턴에 대한 pycubrid 드라이버 제한
- **미지원 DDL (6건):** CUBRID가 지원하지 않는 작업 (예: 특정 경우의 ALTER COLUMN TYPE)
- **카탈로그 쿼리 차이 (4건):** 테스트가 기대하는 것과 다른 CUBRID 카탈로그 뷰
- **예약어 충돌 (2건):** `data` 컬럼명이 CUBRID 예약어와 충돌하여 발생하는 오류. 테스트 테이블에서 `data`를 컬럼명으로 사용할 때 인용 없이 사용하면 구문 오류가 발생합니다.

## 우회 방법

### RETURNING 절 대체

INSERT 후 자동 생성된 ID를 얻으려면 `cursor.lastrowid`를 사용합니다:

```python
with engine.connect() as conn:
    result = conn.execute(
        users.insert().values(name="Alice")
    )
    new_id = result.inserted_primary_key[0]
    conn.commit()
```

### 임시 테이블 대체

정리가 포함된 일반 테이블을 사용합니다:

```python
temp_name = f"tmp_{session_id}"
conn.execute(text(f"CREATE TABLE {temp_name} (id INT, data VARCHAR(100))"))
# ... 테이블 사용 ...
conn.execute(text(f"DROP TABLE IF EXISTS {temp_name}"))
```

### 마이크로초 정밀도 대체

저장 전에 datetime 값을 밀리초로 반올림합니다:

```python
import datetime

def round_to_millis(dt):
    """datetime을 밀리초 정밀도로 반올림합니다."""
    micro = dt.microsecond
    millis = (micro // 1000) * 1000
    return dt.replace(microsecond=millis)
```

### BOOLEAN 컬럼 대체

필요한 경우 명시적 정수 값을 사용합니다:

```python
# 원시 SQL에서 True/False 대신:
conn.execute(text("INSERT INTO t (active) VALUES (1)"))  # True
conn.execute(text("INSERT INTO t (active) VALUES (0)"))  # False
```
