# sqlalchemy-cubrid

**SQLAlchemy 2.x 용 CUBRID dialect**

sqlalchemy-cubrid는 Python에서 CUBRID 객체-관계형 데이터베이스에 대한 완전한 접근을 제공하는 SQLAlchemy dialect 플러그인입니다. [pycubrid](https://pypi.org/project/pycubrid/) 순수 Python 드라이버를 통해 CUBRID 10.2부터 11.4 버전까지 지원합니다.

## 주요 기능

- **SQLAlchemy 2.x 완벽 호환** -- 최신 SQLAlchemy API, ORM, Core와 함께 사용할 수 있습니다
- **DDL 생성** -- CREATE/DROP TABLE, AUTO_INCREMENT, SERIAL (시퀀스), 인덱스 (UNIQUE, REVERSE, FILTERED, FUNCTION 기반), 테이블/컬럼 코멘트
- **완전한 타입 시스템** -- ENUM, JSON, 컬렉션 타입 (SET, MULTISET, LIST), 밀리초 정밀도 DATETIME을 포함한 모든 CUBRID 타입 매핑
- **CUBRID 전용 DML** -- INSERT ... ON DUPLICATE KEY UPDATE, REPLACE INTO, FOR UPDATE OF, TRUNCATE TABLE
- **계층적 쿼리** -- Oracle 스타일의 CONNECT BY / START WITH / ORDER SIBLINGS BY, ROWNUM 의사 컬럼
- **MERGE 구문** -- MERGE INTO ... USING ... ON ... WHEN MATCHED (UPDATE / DELETE) / WHEN NOT MATCHED, 조건부 WHEN 절
- **객체-관계형 기능** -- 클래스 상속 (UNDER), OID 참조 및 경로 표현식 역참조
- **컬렉션 타입** -- CubridSet, CubridMultiset, CubridList와 자동 바이너리 포맷 파싱
- **클릭 카운터** -- INCR() / DECR() 원자적 카운터 함수
- **내장 함수** -- NVL, NVL2, DECODE, IF, IFNULL, GROUP_CONCAT
- **REGEXP 연산자** -- CUBRID의 REGEXP / RLIKE를 위한 `column.regexp_match()` 지원
- **파티셔닝** -- RANGE, HASH, LIST 파티션 DDL 지원
- **DBLINK** -- CREATE SERVER 및 DBLINK()를 통한 원격 데이터베이스 접근 (11.2+)
- **CAST 타입 매핑** -- `CAST(x AS TEXT)`가 CUBRID 호환을 위해 자동으로 `CAST(x AS STRING)`으로 변환
- **인트로스펙션** -- 테이블, 뷰, 컬럼, 인덱스, 외래 키 (ON DELETE/UPDATE 액션 포함), 시퀀스, 코멘트, 상속, OID 컬럼에 대한 완전한 Inspector 지원
- **Alembic 통합** -- 컬렉션 타입 렌더링 및 비교를 포함한 마이그레이션 지원
- **쿼리 추적** -- 성능 분석을 위한 내장 SET TRACE ON / SHOW TRACE 래퍼
- **연결 관리** -- 격리 수준, 연결 풀링, ping, 연결 끊김 감지

## 빠른 설치

```bash
pip install sqlalchemy-cubrid
```

또는 Poetry를 사용하는 경우:

```bash
poetry add sqlalchemy-cubrid
```

## 빠른 시작

```python
from sqlalchemy import create_engine, text

engine = create_engine("cubrid://dba:@localhost:33000/testdb")

with engine.connect() as conn:
    result = conn.execute(text("SELECT 1 FROM db_root"))
    print(result.scalar())  # 1
```

## 문서

| 섹션 | 설명 |
|------|------|
| [시작하기](getting-started.md) | 설치, Docker 설정, 첫 연결 |
| [연결](connection.md) | 엔진 URL, 격리 수준, 풀링 |
| [타입](types.md) | CUBRID와 SQLAlchemy 간의 타입 매핑 |
| [DDL](ddl.md) | 테이블, 시퀀스, 인덱스, 코멘트 |
| [DML](dml.md) | INSERT ON DUPLICATE KEY, REPLACE, FOR UPDATE |
| [쿼리](queries.md) | 계층적 쿼리, MERGE, 클릭 카운터 |
| [CUBRID 기능](cubrid-features.md) | 컬렉션, 상속, OID 참조 |
| [인트로스펙션](introspection.md) | Inspector 메서드 및 리플렉션 |
| [Alembic](alembic.md) | 마이그레이션 지원 및 쿼리 추적 |
| [제한 사항](limitations.md) | 알려진 제한 사항 및 테스트 스위트 결과 |

## 링크

- **소스 코드:** [github.com/cubrid-sqlalchemy/sqlalchemy-cubrid](https://github.com/cubrid-sqlalchemy/sqlalchemy-cubrid)
- **CUBRID 문서:** [cubrid.org/manual/ko/11.4/](https://www.cubrid.org/manual/ko/11.4/)
- **PyPI:** [pypi.org/project/sqlalchemy-cubrid/](https://pypi.org/project/sqlalchemy-cubrid/)
- **pycubrid 드라이버:** [pypi.org/project/pycubrid/](https://pypi.org/project/pycubrid/)

## 라이선스

MIT License. 자세한 내용은 [LICENSE](https://github.com/cubrid-sqlalchemy/sqlalchemy-cubrid/blob/main/LICENSE)를 참조하십시오.
