-- 기존 DB용 마이그레이션: 3모드 촬영 계약 (session.mode + tb_capture)
-- 전제: 2026-08-31_rt_snapshot.sql 이후 적용. 신규 설치는 tryangle-init.sql에 포함됨.
-- 기존 세션 행은 전부 커머스 플로우였으므로 default 'fashion_ref'가 사실과 일치.

ALTER TABLE tb_session
	MODIFY imgId BIGINT NULL COMMENT 'Reference image used (FK to tb_img, NULL for direct mode)',
	ADD COLUMN mode VARCHAR(16) NOT NULL DEFAULT 'fashion_ref' COMMENT 'Entry flow: fashion_ref | aesthetic_ref | direct (soft enum, doc-managed)' AFTER imgId,
	ADD KEY idx_tb_session_mode_date (mode, sDate) COMMENT 'Admin per-mode listing/statistics';

CREATE TABLE IF NOT EXISTS tb_capture (
	id BIGINT NOT NULL AUTO_INCREMENT,
	userId BIGINT NOT NULL COMMENT 'Capture creator (FK to tb_user)',
	sId VARCHAR(32) NULL COMMENT 'Linked session (FK to tb_session, telemetry join key, SET NULL on delete)',
	imgId BIGINT NULL COMMENT 'Reference image (FK to tb_img, set for aesthetic_ref captures)',
	mode VARCHAR(16) NOT NULL COMMENT 'Effective state at shutter: aesthetic_ref | direct | ai_director (soft enum)',
	captureUrl VARCHAR(500) NOT NULL COMMENT 'S3 file path from files/create (type=capture)',
	analysis JSON NULL COMMENT 'Shutter-moment judgement summary - unvalidated, schema owned by SDK',
	capturedAt BIGINT NOT NULL COMMENT 'Capture timestamp (unix ms, per SDK v6 convention)',
	cDate BIGINT NOT NULL COMMENT 'Record creation timestamp (unix sec)',
	uDate BIGINT NOT NULL COMMENT 'Last modification timestamp (unix sec)',
	PRIMARY KEY (id),
	KEY idx_tb_capture_user_mode_time (userId, mode, capturedAt),
	KEY idx_tb_capture_sId (sId),
	KEY idx_tb_capture_imgId (imgId),
	CONSTRAINT fk_tb_capture_userId FOREIGN KEY (userId) REFERENCES tb_user (id)
		ON DELETE RESTRICT ON UPDATE CASCADE,
	CONSTRAINT fk_tb_capture_sId FOREIGN KEY (sId) REFERENCES tb_session (id)
		ON DELETE SET NULL ON UPDATE CASCADE,
	CONSTRAINT fk_tb_capture_imgId FOREIGN KEY (imgId) REFERENCES tb_img (id)
		ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
	COMMENT 'General capture results (aesthetic/direct/AI-director) - non-commerce photo archive';
