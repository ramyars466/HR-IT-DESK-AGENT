-- GoAified HR & IT Helpdesk Database Schema
-- Compatible with PostgreSQL 13+ (and SQLite for local standalone development)

DROP TABLE IF EXISTS it_tickets;
DROP TABLE IF EXISTS employees;

-- 1. Employees Table
CREATE TABLE employees (
    id SERIAL PRIMARY KEY,
    employee_id VARCHAR(32) UNIQUE NOT NULL,
    name VARCHAR(128) NOT NULL,
    email VARCHAR(128) UNIQUE NOT NULL,
    role VARCHAR(128) NOT NULL,
    department VARCHAR(64) NOT NULL,
    casual_leave_balance INTEGER NOT NULL DEFAULT 12,
    sick_leave_balance INTEGER NOT NULL DEFAULT 10,
    earned_leave_balance INTEGER NOT NULL DEFAULT 15,
    joining_date DATE NOT NULL,
    manager_name VARCHAR(128) NOT NULL
);

-- 2. IT Tickets Table
CREATE TABLE it_tickets (
    id SERIAL PRIMARY KEY,
    ticket_id VARCHAR(32) UNIQUE NOT NULL,
    employee_id VARCHAR(32) NOT NULL,
    issue_type VARCHAR(64) NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'OPEN',
    priority VARCHAR(16) NOT NULL DEFAULT 'MEDIUM',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE
);

-- Seed Data: Employees
INSERT INTO employees (employee_id, name, email, role, department, casual_leave_balance, sick_leave_balance, earned_leave_balance, joining_date, manager_name)
VALUES
    ('EMP001', 'Rahul Sharma', 'rahul.sharma@goaified.com', 'AI Engineer Intern', 'AI Agent Studio', 8, 7, 12, '2026-06-01', 'Alok Sharma'),
    ('EMP101', 'Ramya RS', 'ramya.rs@goaified.com', 'AI Engineer', 'AI Engineering', 8, 5, 12, '2026-06-01', 'Alok Sharma'),
    ('EMP102', 'Arjun Mehta', 'arjun.mehta@goaified.com', 'Product Manager', 'Product', 3, 2, 8, '2025-09-01', 'Vikram Mehta'),
    ('EMP002', 'Priya Patel', 'priya.patel@goaified.com', 'Senior Full Stack Engineer', 'Platform Engineering', 4, 9, 14, '2025-02-15', 'Vikram Mehta'),
    ('EMP003', 'Ananya Rao', 'ananya.rao@goaified.com', 'Product Designer', 'Design & UX', 11, 8, 10, '2025-08-01', 'Rohit Sen'),
    ('EMP004', 'Karan Verma', 'karan.verma@goaified.com', 'DevOps & Cloud Engineer', 'Infrastructure', 6, 6, 8, '2024-11-10', 'Vikram Mehta'),
    ('EMP005', 'Sneha Kulkarni', 'sneha.kulkarni@goaified.com', 'QA & Automation Engineer', 'AI Agent Studio', 9, 10, 15, '2026-01-05', 'Alok Sharma');

-- Seed Data: Sample IT Tickets
INSERT INTO it_tickets (ticket_id, employee_id, issue_type, description, status, priority, created_at, updated_at)
VALUES
    ('IT-1000', 'EMP101', 'VPN Connectivity', 'VPN certificate expired on Windows laptop', 'In Progress', 'HIGH', '2026-11-18 11:00:00', '2026-11-18 11:30:00'),
    ('IT-1001', 'EMP001', 'Hardware Access', 'Request for 4K external monitor for multi-agent debugging', 'RESOLVED', 'MEDIUM', '2026-07-10 10:30:00', '2026-07-12 16:45:00'),
    ('IT-1002', 'EMP001', 'Software Access', 'Requesting Docker Pro license key and GCP project quota expansion', 'IN_PROGRESS', 'HIGH', '2026-11-15 09:15:00', '2026-11-16 11:20:00'),
    ('IT-1003', 'EMP002', 'VPN Connectivity', 'Intermittent TLS handshake dropouts on home Wi-Fi network', 'RESOLVED', 'HIGH', '2026-10-02 14:00:00', '2026-10-02 17:30:00'),
    ('IT-1004', 'EMP004', 'Access Permissions', 'Admin rights setup for staging Kubernetes cluster', 'RESOLVED', 'CRITICAL', '2026-09-20 08:00:00', '2026-09-20 09:30:00');
