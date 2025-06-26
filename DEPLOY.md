# Deploying PyExec on Self-Hosting Platforms

This guide covers deployment on platforms like Dokploy, Coolify, CapRover, and similar self-hosting solutions.

## 🚨 Important Requirements

PyExec requires **Docker socket access** to create disposable containers for code execution. This is a privileged operation that some platforms may restrict for security reasons.

## 📦 Deployment Options

### Option 1: Standard Deployment (If Docker Socket is Allowed)

1. **Use the provided `docker-compose.platform.yml`**

   ```bash
   # In your platform, deploy using:
   docker-compose.platform.yml
   ```

2. **Set Required Environment Variables**

   ```env
   API_KEY=your-secure-api-key-here
   ```

3. **Optional Environment Variables**

   ```env
   # For Redis support
   REDIS_URL=redis://redis:6379/0

   # For S3 support
   S3_BUCKET_NAME=your-bucket
   AWS_ACCESS_KEY_ID=your-key
   AWS_SECRET_ACCESS_KEY=your-secret
   AWS_REGION=us-east-1
   ```

### Option 2: Using Docker-in-Docker (DinD)

If the platform doesn't allow Docker socket mounting, you can use Docker-in-Docker:

```yaml
version: "3.8"

services:
  # Docker-in-Docker service
  dind:
    image: docker:24-dind
    container_name: pyexec-dind
    privileged: true
    environment:
      - DOCKER_TLS_CERTDIR=/certs
    volumes:
      - docker-certs-ca:/certs/ca
      - docker-certs-client:/certs/client
      - pyexec-data:/tmp/sessions
    networks:
      - pyexec-network

  app:
    image: ghcr.io/kacperkwapisz/pyexec/pyexec:latest
    container_name: pyexec
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      # Connect to DinD instead of host Docker
      - DOCKER_HOST=tcp://dind:2376
      - DOCKER_TLS_VERIFY=1
      - DOCKER_CERT_PATH=/certs/client
      - API_KEY=${API_KEY}
      - BASE_SESSION_PATH=/tmp/sessions
      - BASE_IMAGE_NAME=ghcr.io/kacperkwapisz/pyexec/pyexec-base:latest
    volumes:
      - docker-certs-client:/certs/client:ro
      - pyexec-data:/tmp/sessions
    depends_on:
      - dind
    networks:
      - pyexec-network

volumes:
  docker-certs-ca:
  docker-certs-client:
  pyexec-data:

networks:
  pyexec-network:
    driver: bridge
```

### Option 3: Alternative Execution Backends

If Docker socket access is completely unavailable, consider these alternatives:

1. **Use Kubernetes Jobs API**

   - Deploy on a Kubernetes cluster
   - Modify PyExec to create K8s Jobs instead of Docker containers

2. **Use Firecracker or gVisor**

   - Lightweight VM or sandbox alternatives
   - Requires platform support

3. **Use WASM Runtime**
   - Run Python via Pyodide in a WASM sandbox
   - More limited but highly secure

## 🚀 Platform-Specific Instructions

### Dokploy

1. Create a new project in Dokploy
2. Select "Docker Compose" deployment
3. Upload `docker-compose.platform.yml`
4. Set environment variables in the Dokploy UI:
   - `API_KEY` (required)
   - Other optional variables
5. Deploy the application

**Note**: Check if Dokploy allows Docker socket mounting in their security settings.

### Coolify

1. Add a new service in Coolify
2. Choose "Docker Compose" as the source
3. Paste the contents of `docker-compose.platform.yml`
4. Configure environment variables:
   ```
   API_KEY=generate-a-secure-key
   ```
5. Enable "Privileged" mode if using Docker socket
6. Deploy

### CapRover

1. Create a new app in CapRover
2. Use the CapRover definition file:

```json
{
  "schemaVersion": 2,
  "dockerfileLines": ["FROM ghcr.io/kacperkwapisz/pyexec/pyexec:latest"],
  "volumes": [
    {
      "containerPath": "/tmp/sessions",
      "volumeName": "pyexec-data"
    },
    {
      "containerPath": "/var/run/docker.sock",
      "hostPath": "/var/run/docker.sock"
    }
  ],
  "env": {
    "API_KEY": "$$cap_api_key",
    "BASE_SESSION_PATH": "/tmp/sessions",
    "BASE_IMAGE_NAME": "ghcr.io/kacperkwapisz/pyexec/pyexec-base:latest"
  }
}
```

## 🔒 Security Considerations

1. **API Key**: Always use a strong, randomly generated API key
2. **Network Isolation**: Consider placing PyExec in an isolated network
3. **Resource Limits**: The platform should enforce resource limits on the PyExec container
4. **Monitoring**: Enable platform monitoring and alerts
5. **Updates**: Regularly update the PyExec images

## 🐛 Troubleshooting

### "Cannot connect to Docker daemon"

**Cause**: Docker socket is not accessible
**Solution**:

- Check if the platform allows Docker socket mounting
- Try the Docker-in-Docker alternative
- Contact platform support about Docker API access

### "Permission denied on /var/run/docker.sock"

**Cause**: Socket permissions issue
**Solution**:

- Some platforms may require adding the container user to the docker group
- Try running with elevated privileges (security trade-off)

### "Image not found: pyexec-base"

**Cause**: The base image isn't accessible
**Solution**:

- Ensure the platform can pull from GitHub Container Registry
- Pre-pull the image: `docker pull ghcr.io/kacperkwapisz/pyexec/pyexec-base:latest`

## 📊 Performance Tips

1. **Use Redis**: If the platform supports it, add Redis for better performance
2. **Use S3**: For multi-instance deployments, use S3 for shared file storage
3. **Resource Allocation**: Allocate at least 1GB RAM to the PyExec container
4. **Volume Performance**: Use SSD-backed volumes for `/tmp/sessions`

## 🆘 Getting Help

If you encounter issues:

1. Check the application logs in your platform's dashboard
2. Verify all environment variables are set correctly
3. Test Docker socket access with: `docker run -v /var/run/docker.sock:/var/run/docker.sock docker:cli docker ps`
4. Open an issue on the PyExec GitHub repository with platform details
