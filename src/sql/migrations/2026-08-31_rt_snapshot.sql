-- 기존 DB용 마이그레이션: 텔레메트리 수신 테이블 (system/send 복원 건)
-- 전제: tb_session 존재. 신규 설치는 tryangle-init.sql에 이미 포함됨.
CREATE TABLE IF NOT EXISTS tb_rt_snapshot (
	-- Composite identity: one row = one second-batch of one session
	sId VARCHAR(32) NOT NULL COMMENT 'Session ID (FK to tb_session, maps app telemetry)',
	secSeq INT NOT NULL COMMENT 'N-th second of the session (starts at 1)',

	-- Batch timing (derived from frame tids, unix ms)
	sDate BIGINT NULL COMMENT 'First frame tid in batch (unix ms)',
	eDate BIGINT NULL COMMENT 'Last frame tid in batch (unix ms)',

	-- Flattened summary columns for session/list filters & aggregates
	-- (derived at ingest: category/feedback = last valued frame, stuckSec = batch max,
	--  canCapture = 'true' if any frame allowed capture)
	category VARCHAR(64) NULL COMMENT 'Judgement category of the second (e.g. pitch, pose)',
	feedback VARCHAR(500) NULL COMMENT 'Last guide feedback message of the second',
	stuckSec FLOAT NULL COMMENT 'Max stuck seconds within the batch',
	canCapture VARCHAR(5) NULL COMMENT 'true/false — whether capture was allowed in the second',

	-- Full fidelity payload: {"records": [v6 frames as sent]}
	rawPayload JSON NOT NULL COMMENT 'Verbatim frame batch (server does not validate bodies)',

	cDate BIGINT NOT NULL COMMENT 'Ingest timestamp (unix sec)',

	PRIMARY KEY (sId, secSeq),
	CONSTRAINT fk_tb_rt_snapshot_sId FOREIGN KEY (sId) REFERENCES tb_session (id)
		ON DELETE CASCADE ON UPDATE CASCADE
	-- CASCADE: session logs have no meaning without their session
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
	COMMENT 'Realtime coaching telemetry - per-second frame batches from the app';
