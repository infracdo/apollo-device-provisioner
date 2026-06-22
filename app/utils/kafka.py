"""
Kafka Utilities

Helper functions for publishing messages to Kafka topics.
"""
import os
import json
import logging
from typing import Dict, Any, Optional
from kafka import KafkaProducer
from kafka.errors import KafkaError

logger = logging.getLogger(__name__)


class KafkaPublisher:
    """Kafka message publisher"""
    
    _instance = None
    _producer = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(KafkaPublisher, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._producer is None:
            self._initialize_producer()
    
    def _initialize_producer(self):
        """Initialize Kafka producer"""
        try:
            bootstrap_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', '10.42.4.19:9092')
            
            self._producer = KafkaProducer(
                bootstrap_servers=bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks='all',
                retries=3
            )
            logger.info(f"✅ Kafka producer initialized: {bootstrap_servers}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Kafka producer: {e}")
            self._producer = None
    
    def publish(self, topic: str, message: Dict[str, Any]) -> bool:
        """
        Publish message to Kafka topic
        
        Args:
            topic: Kafka topic name
            message: Message dictionary to publish
        
        Returns:
            bool: True if published successfully, False otherwise
        """
        if self._producer is None:
            logger.error("Kafka producer not initialized")
            return False
        
        try:
            future = self._producer.send(topic, message)
            future.get(timeout=10)
            logger.info(f"✅ Published to Kafka topic '{topic}'")
            return True
        except KafkaError as e:
            logger.error(f"❌ Kafka error publishing to topic '{topic}': {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to publish to Kafka topic '{topic}': {e}")
            return False
    
    def close(self):
        """Close Kafka producer"""
        if self._producer:
            self._producer.close()
            logger.info("Kafka producer closed")


# Singleton instance
kafka_publisher = KafkaPublisher()


def publish_to_kafka(topic: str, message: Dict[str, Any]) -> bool:
    """
    Convenience function to publish message to Kafka
    
    Args:
        topic: Kafka topic name
        message: Message dictionary to publish
    
    Returns:
        bool: True if published successfully, False otherwise
    """
    return kafka_publisher.publish(topic, message)
