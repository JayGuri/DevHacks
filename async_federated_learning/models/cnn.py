"""
models/cnn.py
=============
Convolutional neural network model definition for CIFAR-10 classification.

Will contain:
- SimpleCNN class: a lightweight CNN (conv → pool → conv → pool → fc layers)
  suitable for CIFAR-10; serves as the shared global model in the FL pipeline.
- get_model() factory function returning a fresh model instance.
- Parameter count utility for logging model size.
"""
