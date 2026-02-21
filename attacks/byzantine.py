# attacks/byzantine.py — MaliciousTrainer: sign-flip amplified Byzantine attack
import asyncio
import random
import logging
import numpy as np
import torch
import torch.nn as nn

logger = logging.getLogger("fedbuff.attacks")


class MaliciousTrainer:
    """
    Sign-flip amplified Byzantine attack.
    Trains genuinely to produce plausible local_loss values,
    then scales the weight diff by attack_scale to corrupt the gradient direction.
    The attack is not detectable by loss monitoring alone because local_loss is unmodified.
    """

    def __init__(
        self,
        model: nn.Module,
        global_weights: dict,
        mu: float = 0.01,
        lr: float = 0.01,
        epochs: int = 5,
        device: str = "cpu",
        attack_scale: float = -5.0,
    ):
        self.model = model
        self.global_weights = global_weights
        self.mu = mu
        self.lr = lr
        self.epochs = epochs
        self.device = device
        self.attack_scale = attack_scale
        self.heartbeat_delay = (0.5, 3.0)

    def _honest_train(self, data_loader) -> dict:
        """
        Runs the FedProx training loop honestly:
          loss = CrossEntropy(output, y) + (mu/2) * sum(||w_i - w0_i||^2)
        Returns {"loss": float, "weight_diff": dict_of_numpy, "num_samples": int}
        """
        self.model.to(self.device)
        self.model.train()

        # Load global weights into model
        global_tensors = {}
        for name, param in self.model.named_parameters():
            if name in self.global_weights:
                param.data.copy_(torch.tensor(self.global_weights[name], dtype=param.dtype).to(self.device))
            global_tensors[name] = param.data.clone()

        optimizer = torch.optim.SGD(self.model.parameters(), lr=self.lr)
        criterion = nn.CrossEntropyLoss()

        total_loss = 0.0
        total_samples = 0

        for epoch in range(self.epochs):
            for batch_x, batch_y in data_loader:
                batch_x = batch_x.to(self.device)
                batch_y = batch_y.to(self.device)

                optimizer.zero_grad()
                output = self.model(batch_x)

                # Handle Shakespeare output shape: (B, 80, 80) -> reshape for CE
                if output.dim() == 3:
                    output = output.view(-1, output.size(-1))
                    batch_y = batch_y.view(-1)

                ce_loss = criterion(output, batch_y)

                # FedProx proximal term
                prox_loss = 0.0
                for name, param in self.model.named_parameters():
                    if name in global_tensors:
                        prox_loss += torch.sum((param - global_tensors[name]) ** 2)
                prox_loss = (self.mu / 2.0) * prox_loss

                loss = ce_loss + prox_loss
                loss.backward()
                optimizer.step()

                total_loss += ce_loss.item() * batch_x.size(0)
                total_samples += batch_x.size(0)

        # Compute weight diff
        weight_diff = {}
        for name, param in self.model.named_parameters():
            if name in self.global_weights:
                weight_diff[name] = (
                    param.data.cpu().numpy() - self.global_weights[name]
                )

        avg_loss = total_loss / max(total_samples, 1)
        return {
            "loss": avg_loss,
            "weight_diff": weight_diff,
            "num_samples": total_samples,
        }

    async def train(self, data_loader) -> dict:
        """
        1. result = await asyncio.to_thread(self._honest_train, data_loader)
        2. Multiply every value in result["weight_diff"] by self.attack_scale.
        3. result["local_loss"] is NOT modified (stays as honest loss).
        4. Simulate async heartbeat: await asyncio.sleep(random.uniform(0.5, 3.0))
        5. Return corrupted result.
        """
        result = await asyncio.to_thread(self._honest_train, data_loader)

        # Apply sign-flip amplification attack to weight diffs
        corrupted_diff = {}
        for key, val in result["weight_diff"].items():
            corrupted_diff[key] = val * self.attack_scale

        logger.info(
            "MaliciousTrainer: applied sign-flip amplified attack (scale=%.1f)",
            self.attack_scale,
        )

        # Simulate async heartbeat delay
        delay = random.uniform(*self.heartbeat_delay)
        await asyncio.sleep(delay)

        return {
            "loss": result["loss"],  # local_loss is NOT modified
            "local_loss": result["loss"],
            "weight_diff": corrupted_diff,
            "num_samples": result["num_samples"],
        }
