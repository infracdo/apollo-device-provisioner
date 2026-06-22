# Apollo Device Provisioner API

A comprehensive, device-agnostic network provisioning API built with FastAPI that provides unified interfaces for managing network infrastructure including OLTs, switches, routers, and more.

## 🚀 Features

### Multi-Vendor Device Support

#### **OLT (Optical Line Terminal) Management**
- **Supported Vendors**: Huawei, BDCOM, ZTE, SmartOLT, RicherLink
- ONU/ONT provisioning, removal, and status monitoring
- Unconfigured ONU discovery
- Profile management (T-CONT, VLAN, Service)
- Port information and statistics
- Board and VLAN configuration
- Automated ONU registration workflow
- Offline ONU cleanup

#### **Network Switch Management**
- **Supported Vendors**: Ruijie, Cisco Nexus, Arista
- Interface configuration and monitoring
- VLAN management (create, assign, trunk)
- MAC address and ARP table queries
- Configuration backup and restore
- Port security and status control
- Device capability discovery

#### **MikroTik Router Management**
- Queue management (bandwidth shaping)
- Hotspot user provisioning
- PPPoE session management
- API and RouterOS integration

### PPPoE & User Management

- **User Lifecycle Management**: Create, update, delete, activate, deactivate
- **RADIUS Integration**: 
  - CoA (Change of Authorization) for real-time session updates
  - Disconnect-Request for forced disconnection
  - Accounting and session tracking
- **Billing Integration**: Overdue payment handling with captive portal
- **ONU Binding**: Link PPPoE users to physical ONU devices
- **WiFi Configuration**: Remote WiFi configuration via GenieACS/TR-069
- **Data Caps**: Configurable upload/download limits (Gigawords)

### Advanced Features

- **Kafka Event Integration**: Async event-driven workflows for provisioning
- **GenieACS Integration**: TR-069/CWMP device management for ONUs
- **RADIUS Accounting**: Session tracking, bandwidth monitoring
- **SNMP Support**: Device monitoring and trap handling
- **Ansible Integration**: Configuration management automation
- **Multi-Protocol Support**: SSH, Telnet, API, SNMP
- **Database-Driven**: PostgreSQL with SQLAlchemy ORM
- **RESTful API**: Comprehensive OpenAPI/Swagger documentation
- **Docker Ready**: Production-ready containerization

## 📋 Requirements

- **Python**: 3.10+
- **PostgreSQL**: 13+
- **Redis**: 6+
- **Kafka**: 2.8+ (optional, for event-driven features)
- **Docker & Docker Compose** (recommended)

## 🔧 Installation

### Option 1: Docker Compose (Recommended)

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd apollo-device-provisioner
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   nano .env
   ```

3. **Start services**
   ```bash
   docker-compose up -d
   ```

4. **Run database migrations**
   ```bash
   docker-compose exec api alembic upgrade head
   ```

5. **Access the API**
   - API: http://localhost:8000
   - Documentation: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

### Option 2: Local Development

1. **Clone and setup**
   ```bash
   git clone <repository-url>
   cd apollo-device-provisioner
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your database and service URLs
   ```

4. **Setup PostgreSQL database**
   ```bash
   createdb device_provisioning
   ```

5. **Run migrations**
   ```bash
   alembic upgrade head
   ```

6. **Start the application**
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

## ⚙️ Configuration

### Environment Variables

Key configuration options in `.env`:

```bash
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/device_provisioning

# Redis (for caching and Celery)
REDIS_URL=redis://localhost:6379/0

# Kafka (for event-driven workflows)
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Application
DEBUG=False
SECRET_KEY=<generate-secure-key>
API_V1_PREFIX=/api/v1

# Device Connection
DEFAULT_SSH_PORT=22
DEFAULT_TELNET_PORT=23
DEFAULT_CONNECTION_TIMEOUT=30
ENABLE_SSL_VERIFICATION=False

# Security
ENCRYPT_DEVICE_CREDENTIALS=True
CREDENTIAL_ENCRYPTION_KEY=<generate-encryption-key>
```

### Generating Secrets

```bash
# Generate SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate CREDENTIAL_ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 📚 API Documentation

### Interactive Documentation

Once running, access the interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

### Quick Start Examples

#### 1. Add a Device

```bash
curl -X POST "http://localhost:8000/api/v1/devices/" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "OLT-Main-01",
    "manufacturer": "zte",
    "device_type": "olt",
    "host": "10.42.3.24",
    "port": 22,
    "protocol": "ssh",
    "username": "admin",
    "password": "password",
    "is_active": true
  }'
```

#### 2. Get ONU Status

```bash
curl "http://localhost:8000/api/v1/olt/onu/1/status"
```

#### 3. Provision an ONU

```bash
curl -X POST "http://localhost:8000/api/v1/olt/provision-onu" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": 1,
    "onu_config": {
      "serial_no": "MHAR08DF4BD9",
      "slot": 1,
      "port": 2,
      "line_profile_id": 1,
      "service_profile_id": 1,
      "vlan": 100,
      "description": "Customer ABC"
    }
  }'
```

#### 4. Create PPPoE User

```bash
curl -X POST "http://localhost:8000/api/v1/pppoe/users" \
  -H "Content-Type: application/json" \
  -d '{
    "user_name": "user001@isp.com",
    "user_password": "password",
    "nas_ip_address": "10.42.10.5",
    "mikrotik_rate_limit": "20M/20M",
    "onu_serial_number": "MHAR08DF4BD9",
    "is_active": true
  }'
```

## 🗄️ Database

### Migrations

The project uses Alembic for database migrations.

```bash
# Create a new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history

# View current version
alembic current
```

### Database Schema

Main tables:
- `devices` - Network devices (OLTs, switches, routers)
- `pppoe_users` - PPPoE user accounts
- `pppoe_accounting_requests` - RADIUS accounting records
- Device-specific tables for profiles, configurations

## 🏗️ Architecture

```
apollo-device-provisioner/
├── app/
│   ├── adapters/          # Device-specific adapters (Huawei, ZTE, etc.)
│   ├── api/               # API endpoints
│   │   └── v1/           # API version 1 routes
│   ├── connectors/        # Connection handlers (SSH, Telnet, API)
│   ├── models/            # SQLAlchemy database models
│   ├── schemas/           # Pydantic schemas for validation
│   ├── services/          # Business logic services
│   ├── utils/             # Utility functions
│   ├── config.py          # Application configuration
│   ├── database.py        # Database setup
│   └── main.py            # FastAPI application entry point
├── alembic/               # Database migrations
├── ansible/               # Ansible playbooks (optional)
├── .gitlab/               # GitLab CI/CD configuration
├── Dockerfile             # Docker image definition
├── docker-compose.yml     # Docker Compose configuration
├── requirements.txt       # Python dependencies
└── .env.example          # Environment variables template
```

### Key Components

#### Adapters
Device-specific implementations for different manufacturers:
- `HuaweiAdapter` - Huawei OLT commands
- `ZTEAdapter` - ZTE OLT commands
- `BDCOMAdapter` - BDCOM OLT commands
- `RuijieAdapter` - Ruijie switch commands
- `MikrotikAdapter` - MikroTik router commands

#### Connectors
Protocol handlers for device communication:
- `SSHConnector` - SSH connections via Paramiko
- `TelnetConnector` - Telnet connections
- `APIConnector` - HTTP/REST API connections
- `SNMPConnector` - SNMP queries and traps

#### Services
Business logic and workflows:
- `DeviceService` - Device management operations
- `OLTService` - OLT-specific operations
- `PPPoEService` - PPPoE user management
- `RADIUSCoAService` - RADIUS CoA operations

## 🚢 Deployment

### Production Docker Deployment

1. **Build the image**
   ```bash
   docker build -t apollo-device-provisioner:latest .
   ```

2. **Push to registry**
   ```bash
   docker tag apollo-device-provisioner:latest registry.example.com/apollo-device-provisioner:latest
   docker push registry.example.com/apollo-device-provisioner:latest
   ```

3. **Deploy with Docker Compose**
   ```bash
   docker-compose -f docker-compose.yml up -d
   ```

### Using GitLab CI/CD

The project includes GitLab CI/CD configuration in `.gitlab/`. It automatically:
- Runs tests
- Builds Docker images
- Pushes to container registry
- Deploys to staging/production

### Build Script

Use the included build script:
```bash
./docker-build-push.sh
```

## 🔐 Security

### Best Practices

1. **Change default secrets**: Generate strong `SECRET_KEY` and `CREDENTIAL_ENCRYPTION_KEY`
2. **Enable credential encryption**: Set `ENCRYPT_DEVICE_CREDENTIALS=True`
3. **Use SSL/TLS**: Enable `ENABLE_SSL_VERIFICATION=True` in production
4. **Secure database**: Use strong PostgreSQL credentials
5. **Network isolation**: Run services in isolated networks
6. **CORS configuration**: Restrict `CORS_ORIGINS` to trusted domains
7. **Rate limiting**: Enable `RATE_LIMIT_ENABLED=True`

### Credential Management

Device credentials are encrypted at rest when `ENCRYPT_DEVICE_CREDENTIALS` is enabled. The encryption key must be kept secure and backed up.

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_device_service.py

# Run with verbose output
pytest -v
```

## 📊 Monitoring

### Health Checks

- **API Health**: `GET /health`
- **Root Endpoint**: `GET /`

### Logging

Logs are written to:
- Console (stdout)
- File: `/app/logs/app.log` (configurable)

Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL

### Metrics

Integration points for monitoring:
- Redis for caching metrics
- Celery Flower for task monitoring (port 5555)
- PostgreSQL query logging

## 🛠️ Development

### Code Structure

Follow these conventions:
- **Adapters**: Device-specific command implementations
- **Services**: Business logic, no direct device communication
- **Schemas**: Request/response validation with Pydantic
- **Models**: Database models with SQLAlchemy

### Adding a New Device Type

1. Create adapter in `app/adapters/`
2. Implement required methods (connect, disconnect, execute_command)
3. Add device type to schemas
4. Create service methods in `app/services/`
5. Add API endpoints in `app/api/v1/`

### Pre-commit Hooks

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

[Specify your license here]

## 📞 Support

For API support and questions:
- **Documentation**: See `APOLLO_DEVICE_PROVISIONER_API_DOCUMENTATION.md`
- **Issues**: [Create an issue on GitLab/GitHub]
- **Email**: [Your support email]

## 🔗 Related Projects

- **GenieACS**: TR-069/CWMP device management
- **Apache Kafka**: Event streaming for async workflows
- **RADIUS Server**: Authentication and accounting

## 📈 Roadmap

- [ ] Add support for more OLT vendors
- [ ] Implement IPOE (IPoE) support
- [ ] Enhanced monitoring dashboard
- [ ] Multi-tenancy support
- [ ] Advanced analytics and reporting
- [ ] Automated failover detection
- [ ] Network topology mapping

## 🙏 Acknowledgments

Built for Apollo Internet Services to provide a unified, device-agnostic provisioning platform for managing diverse network infrastructure.

---

**Version**: 1.0.0  
**Last Updated**: December 2025
