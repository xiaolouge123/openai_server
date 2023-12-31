CREATE DATABASE OpenAIUsage;

USE OpenAIUsage;

CREATE TABLE APIUsageDetails (
    id INT AUTO_INCREMENT PRIMARY KEY,
    apiKey VARCHAR(255),
    billing DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE APIKeys (
    id INT AUTO_INCREMENT PRIMARY KEY,
    apiKey VARCHAR(255),
    comment TEXT,
    available BOOLEAN DEFAULT TRUE,
    usageLimit INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE RequestRecords (
    request_id INT AUTO_INCREMENT PRIMARY KEY,
    apiKey VARCHAR(255),
    modelName VARCHAR(255),
    request_body TEXT NOT NULL,
    prompt_token_count INT NOT NULL,
    generation_token_count INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);
