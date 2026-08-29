-- 기존 DB용 마이그레이션: 닉네임 유일 제약 (2026-08-25 팀 정책)
-- 전제: 실행 시점에 중복 닉네임이 없어야 한다 (있으면 아래 조회로 먼저 확인)
-- SELECT nickname, COUNT(*) FROM tb_user GROUP BY nickname HAVING COUNT(*) > 1;
ALTER TABLE tb_user ADD UNIQUE KEY uk_tb_user_nickname (nickname);
