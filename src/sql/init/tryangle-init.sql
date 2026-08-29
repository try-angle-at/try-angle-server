-- TryAngle Database Schema Initialization Script
-- Target Environment: MySQL 8.0+ with InnoDB Storage Engine
-- Character Set: utf8mb4 (Unicode support)

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

START TRANSACTION;

CREATE TABLE IF NOT EXISTS tb_user (
	-- Primary identifier
	id BIGINT NOT NULL AUTO_INCREMENT,
	
	-- Authentication & Contact
	email VARCHAR(255) NOT NULL COMMENT 'Email address (unique login identifier)',
	password VARCHAR(255) NULL COMMENT 'Hashed password (bcrypt recommended)',
	name VARCHAR(100) NULL COMMENT 'Real name / Full name',
	nickname VARCHAR(100) NULL COMMENT 'Display name for public profile',
	phone VARCHAR(20) NULL COMMENT 'Phone number for contact',
	emailConf VARCHAR(1) NOT NULL DEFAULT '2' COMMENT 'Email verification status (2: pending, 1: verified)',
	
	-- Profile & Metadata
	`desc` TEXT NULL COMMENT 'User biography / description',
	fileId VARCHAR(255) NULL COMMENT 'S3/R2 file path for profile image (profiles/p_userId_*)',
	
	-- Authorization
	role ENUM('SUPER_ADMIN', 'ADMIN', 'CLIENT') NOT NULL DEFAULT 'CLIENT' COMMENT 'User role for access control',
	
	-- Status & Audit
	state INT NOT NULL DEFAULT 1 COMMENT 'Account state (0: disabled, 1: active)',
	extra JSON NULL COMMENT 'Flexible metadata (unstructured extensions)',
	cDate BIGINT NOT NULL COMMENT 'Account creation timestamp (Unix epoch)',
	uDate BIGINT NOT NULL COMMENT 'Last profile update timestamp (Unix epoch)',
	
	PRIMARY KEY (id),
	UNIQUE KEY uk_tb_user_email (email) COMMENT 'Email must be unique for login',
	UNIQUE KEY uk_tb_user_nickname (nickname) COMMENT 'Nickname must be unique (2026-08-25 policy)',
	KEY idx_tb_user_state (state) COMMENT 'Index for filtering active/inactive users',
	CONSTRAINT ck_tb_user_state CHECK (state IN (0, 1)) -- Enforce binary state values
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
	COMMENT 'User account repository - root entity for all access control';

CREATE TABLE IF NOT EXISTS tb_img_ctg (
	-- Primary identifier
	id BIGINT NOT NULL AUTO_INCREMENT,
	
	-- Category Definition
	name VARCHAR(100) NOT NULL COMMENT 'Category name (e.g., "Upper Body", "Accessories")',
	
	-- Audit Timestamps
	cDate BIGINT NOT NULL COMMENT 'Category creation timestamp (Unix epoch)',
	uDate BIGINT NOT NULL COMMENT 'Last update timestamp (Unix epoch)',
	
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
	COMMENT 'Reference image category taxonomy - organizational structure';

CREATE TABLE IF NOT EXISTS tb_img (
	-- Primary identifier
	id BIGINT NOT NULL AUTO_INCREMENT,
	
	-- Ownership & Classification
	userId BIGINT NOT NULL COMMENT 'Image uploader/owner (FK to tb_user)',
	ctgId BIGINT NOT NULL COMMENT 'Image category ID (FK to tb_img_ctg)',
	
	-- Storage & Access
	imgUrl VARCHAR(500) NOT NULL COMMENT 'S3/R2 file path (reference/ref_imgId_timestamp.ext)',
	title VARCHAR(200) NULL COMMENT 'Image title / display name',
	`desc` TEXT NULL COMMENT 'Image description / fitting guidance notes',
	
	-- Ranking & Discovery
	useCnt INT NOT NULL DEFAULT 0 COMMENT 'Reference count (sessions using this image)',
	kwd JSON NULL COMMENT 'Search keywords (JSON array: ["keyword1", "keyword2"])',
	aiDoc JSON NULL COMMENT 'AI analysis output (measurements, recommendations)',
	expWeight FLOAT NOT NULL DEFAULT 0 COMMENT 'ML-based relevance score (0.0-1.0)',
	pri INT NOT NULL DEFAULT 0 COMMENT 'Manual priority ranking (higher = featured)',
	
	-- Audit Timestamps
	cDate BIGINT NOT NULL COMMENT 'Image upload timestamp (Unix epoch)',
	uDate BIGINT NOT NULL COMMENT 'Last modification timestamp (Unix epoch)',
	
	PRIMARY KEY (id),
	KEY idx_tb_img_userId (userId) COMMENT 'Query images by uploader',
	KEY idx_tb_img_ctgId (ctgId) COMMENT 'Query images by category',
	KEY idx_tb_img_rank (useCnt, expWeight, pri) COMMENT 'Composite index for recommendation sorting',
	CONSTRAINT fk_tb_img_userId FOREIGN KEY (userId) REFERENCES tb_user (id)
		ON DELETE RESTRICT ON UPDATE CASCADE, -- Preserve image records with user
	CONSTRAINT fk_tb_img_ctgId FOREIGN KEY (ctgId) REFERENCES tb_img_ctg (id)
		ON DELETE RESTRICT ON UPDATE CASCADE -- Preserve category structure
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
	COMMENT 'Reference image library for fitting guidance - core content repository';

CREATE TABLE IF NOT EXISTS tb_session (
	-- Primary identifier (manually assigned, not auto-increment)
	id VARCHAR(32) NOT NULL COMMENT 'Session ID (manual generation via generate_sid(), maps to external logs)',
	
	-- Session Context
	userId BIGINT NOT NULL COMMENT 'Session participant (FK to tb_user)',
	imgId BIGINT NOT NULL COMMENT 'Reference image used (FK to tb_img)',
	
	-- Timing
	sDate BIGINT NOT NULL COMMENT 'Session start timestamp (Unix epoch)',
	eDate BIGINT NULL COMMENT 'Session end timestamp (Unix epoch, NULL if ongoing)',
	
	-- Metadata
	device JSON NULL COMMENT 'Device info at session time (JSON: {model, os, screen_size, ...})',
	
	-- Status & Audit
	sStat INT NOT NULL DEFAULT 0 COMMENT 'Session state (0: ready, 1: completed, 2: failed)',
	cDate BIGINT NOT NULL COMMENT 'Record creation timestamp (Unix epoch)',
	uDate BIGINT NOT NULL COMMENT 'Last modification timestamp (Unix epoch)',
	
	PRIMARY KEY (id),
	KEY idx_tb_session_userId (userId) COMMENT 'Query sessions by user',
	KEY idx_tb_session_imgId (imgId) COMMENT 'Query sessions by reference image',
	KEY idx_tb_session_status_date (sStat, sDate) COMMENT 'Composite index for status/timeline queries',
	CONSTRAINT fk_tb_session_userId FOREIGN KEY (userId) REFERENCES tb_user (id)
		ON DELETE RESTRICT ON UPDATE CASCADE, -- Preserve session history
	CONSTRAINT fk_tb_session_imgId FOREIGN KEY (imgId) REFERENCES tb_img (id)
		ON DELETE RESTRICT ON UPDATE CASCADE, -- Preserve session-image linkage
	CONSTRAINT ck_tb_session_sStat CHECK (sStat IN (0, 1, 2)) -- Enforce valid state values
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
	COMMENT 'Fitting session tracking - links users, reference images, and results';

CREATE TABLE IF NOT EXISTS tb_prod (
	-- Primary identifier
	id BIGINT NOT NULL AUTO_INCREMENT,
	
	-- Ownership & Metadata
	userId BIGINT NOT NULL COMMENT 'Product creator/owner (FK to tb_user)',
	name VARCHAR(200) NOT NULL COMMENT 'Product name (e.g., "Summer Dress - Blue")',
	brand VARCHAR(300) NULL COMMENT 'Brand/manufacturer name',
	price INT NOT NULL DEFAULT 0 COMMENT 'Price in cents (e.g., 9999 = $99.99)',
	
	-- Storage & Access
	thumbUrl VARCHAR(500) NULL COMMENT 'S3/R2 product thumbnail (products/prod_prodId_timestamp.ext)',
	
	-- Status & Audit
	pStat INT NOT NULL DEFAULT 1 COMMENT 'Product status (0: inactive, 1: active, 2: sold_out)',
	cDate BIGINT NOT NULL COMMENT 'Product listing creation timestamp (Unix epoch)',
	uDate BIGINT NOT NULL COMMENT 'Last modification timestamp (Unix epoch)',
	
	PRIMARY KEY (id),
	KEY idx_tb_prod_userId (userId) COMMENT 'Query products by owner/seller',
	KEY idx_tb_prod_pStat (pStat) COMMENT 'Query active/available products',
	CONSTRAINT fk_tb_prod_userId FOREIGN KEY (userId) REFERENCES tb_user (id)
		ON DELETE RESTRICT ON UPDATE CASCADE, -- Preserve product records
	CONSTRAINT ck_tb_prod_pStat CHECK (pStat IN (0, 1, 2)) -- Enforce valid product status
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
	COMMENT 'Product catalog - items tested/evaluated in fitting sessions';

CREATE TABLE IF NOT EXISTS tb_snap (
	-- Primary identifier
	id BIGINT NOT NULL AUTO_INCREMENT,
	
	-- Relationships
	userId BIGINT NOT NULL COMMENT 'Snapshot creator (FK to tb_user)',
	prodId BIGINT NOT NULL COMMENT 'Product being worn (FK to tb_prod)',
	imgId BIGINT NOT NULL COMMENT 'Reference image used (FK to tb_img)',
	sId VARCHAR(32) NULL COMMENT 'Associated session (FK to tb_session.id VARCHAR(32), nullable, SET NULL on delete)',
	
	-- Storage & Access
	snapUrl VARCHAR(500) NOT NULL COMMENT 'S3/R2 snapshot file (snaps/YYYY/MM/snap_sId_timestamp.webp)',
	
	-- User Feedback & Metrics
	comment TEXT NULL COMMENT 'User review/feedback about the product/fit',
	
	-- Body Metrics (at snapshot time)
	gender INT NOT NULL DEFAULT 0 COMMENT 'Gender (0: unknown, 1: male, 2: female)',
	userH FLOAT NULL COMMENT 'User height (cm)',
	userW FLOAT NULL COMMENT 'User weight (kg)',
	
	-- Engagement
	viewCnt INT NOT NULL DEFAULT 0 COMMENT 'Public view count',
	
	-- Audit Timestamps
	cDate BIGINT NOT NULL COMMENT 'Snapshot creation timestamp (Unix epoch)',
	uDate BIGINT NOT NULL COMMENT 'Last modification timestamp (Unix epoch)',
	
	PRIMARY KEY (id),
	KEY idx_tb_snap_userId (userId) COMMENT 'Query snapshots by creator',
	KEY idx_tb_snap_prodId (prodId) COMMENT 'Query snapshots of a product',
	KEY idx_tb_snap_imgId (imgId) COMMENT 'Query snapshots using reference image',
	UNIQUE KEY uk_tb_snap_sId (sId) COMMENT 'One snapshot per session (NULL allowed for multiple)',
	KEY idx_tb_snap_viewCnt (viewCnt) COMMENT 'Sort by popularity/engagement',
	CONSTRAINT fk_tb_snap_userId FOREIGN KEY (userId) REFERENCES tb_user (id)
		ON DELETE RESTRICT ON UPDATE CASCADE, -- Preserve snapshot when user exists
	CONSTRAINT fk_tb_snap_prodId FOREIGN KEY (prodId) REFERENCES tb_prod (id)
		ON DELETE RESTRICT ON UPDATE CASCADE, -- Preserve snapshot-product link
	CONSTRAINT fk_tb_snap_imgId FOREIGN KEY (imgId) REFERENCES tb_img (id)
		ON DELETE RESTRICT ON UPDATE CASCADE, -- Preserve snapshot-reference link
	CONSTRAINT fk_tb_snap_sId FOREIGN KEY (sId) REFERENCES tb_session (id)
		ON DELETE SET NULL ON UPDATE CASCADE, -- Keep snapshot if session deleted
	CONSTRAINT ck_tb_snap_gender CHECK (gender IN (0, 1, 2)) -- Enforce valid gender values
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
	COMMENT 'Fitting results - user snapshots wearing evaluated products';

CREATE TABLE IF NOT EXISTS mtb_bookmark (
	-- Primary identifier
	id BIGINT NOT NULL AUTO_INCREMENT,
	
	-- Relationship
	userId BIGINT NOT NULL COMMENT 'User who bookmarked (FK to tb_user)',
	imgId BIGINT NOT NULL COMMENT 'Bookmarked image (FK to tb_img)',
	
	-- Audit
	cDate BIGINT NOT NULL COMMENT 'Bookmark creation timestamp (Unix epoch)',
	
	PRIMARY KEY (id),
	UNIQUE KEY uk_mtb_bookmark_user_img (userId, imgId) COMMENT 'User can bookmark each image only once',
	KEY idx_mtb_bookmark_userId (userId) COMMENT 'Query all bookmarks by user',
	KEY idx_mtb_bookmark_imgId (imgId) COMMENT 'Query bookmarking users of an image',
	CONSTRAINT fk_mtb_bookmark_userId FOREIGN KEY (userId) REFERENCES tb_user (id)
		ON DELETE CASCADE ON UPDATE CASCADE, -- Remove bookmarks when user deleted
	CONSTRAINT fk_mtb_bookmark_imgId FOREIGN KEY (imgId) REFERENCES tb_img (id)
		ON DELETE CASCADE ON UPDATE CASCADE -- Remove bookmarks when image deleted
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
	COMMENT 'User bookmarks on reference images (reserved for future implementation)';

CREATE TABLE IF NOT EXISTS mtb_img_tag (
	-- Primary identifier
	id BIGINT NOT NULL AUTO_INCREMENT,
	
	-- Relationship
	imgId BIGINT NOT NULL COMMENT 'Image (FK to tb_img)',
	tagId BIGINT NOT NULL COMMENT 'Tag (FK to tb_tag)',
	
	PRIMARY KEY (id),
	UNIQUE KEY uk_mtb_img_tag_img_tag (imgId, tagId) COMMENT 'Each tag applied to image only once',
	KEY idx_mtb_img_tag_imgId (imgId) COMMENT 'Query all tags applied to an image',
	KEY idx_mtb_img_tag_tagId (tagId) COMMENT 'Query all images with a tag',
	CONSTRAINT fk_mtb_img_tag_imgId FOREIGN KEY (imgId) REFERENCES tb_img (id)
		ON DELETE CASCADE ON UPDATE CASCADE -- Remove tag mappings when image deleted
	-- NOTE: tb_tag 테이블이 아직 정의되지 않아 아래 FK는 보류 (tb_tag 추가 시 복원)
	-- , CONSTRAINT fk_mtb_img_tag_tagId FOREIGN KEY (tagId) REFERENCES tb_tag (id)
	--     ON DELETE CASCADE ON UPDATE CASCADE -- Remove tag mappings when tag deleted
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
	COMMENT 'Image-to-tag mappings (reserved for future implementation)';

COMMIT;

SET FOREIGN_KEY_CHECKS = 1;
