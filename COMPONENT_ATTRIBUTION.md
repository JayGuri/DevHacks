# Component Attribution

This project builds upon the following research contributions and open-source components.

---

## LEAF Benchmark Datasets (FEMNIST, Shakespeare)

**Citation:** Caldas, S., Duddu, S.M.K., Wu, P., Li, T., Konečný, J., McMahan, H.B., Smith, V., and Talwalkar, A.  
**Title:** "LEAF: A Benchmark for Federated Settings"  
**Reference:** arXiv:1812.01097, 2018  
**URL:** https://arxiv.org/abs/1812.01097  
**Usage:** FEMNIST (62-class handwritten character images) and Shakespeare (next-character prediction) datasets are used as the two heterogeneous tasks in our multi-task federated learning demonstration.

---

## FedProx Algorithm

**Citation:** Li, T., Sahu, A.K., Zaheer, M., Sanjabi, M., Talwalkar, A., and Smith, V.  
**Title:** "Federated Optimization in Heterogeneous Networks"  
**Reference:** MLSys 2020  
**URL:** https://arxiv.org/abs/1812.06127  
**Usage:** The FedProx proximal term (mu/2 * ||w - w_global||^2) is used in both the HonestTrainer and MaliciousTrainer to handle statistical heterogeneity across clients.

---

## Multi-Krum (SABD Variant)

**Citation:** Blanchard, P., El Mhamdi, E.M., Guerraoui, R., and Stainer, J.  
**Title:** "Machine Learning with Adversaries: Byzantine Tolerant Gradient Descent"  
**Reference:** NeurIPS 2017  
**URL:** https://proceedings.neurips.cc/paper/2017/hash/f4b9ec30ad9f68f89b29639786cb62ef-Abstract.html  
**Usage:** The Multi-Krum algorithm is implemented in `detection/sabd.py` as the Statistical Anomaly-Based Detection (SABD) second-layer defense, selecting the most trustworthy subset of client updates.

---

## FedBuff — Buffered Asynchronous Aggregation

**Citation:** Nguyen, J., Malik, K., Zhan, H., Yousefpour, A., Rabbat, M., Malek, M., and Huba, D.  
**Title:** "Federated Learning with Buffered Asynchronous Aggregation"  
**Reference:** AISTATS 2022  
**URL:** https://arxiv.org/abs/2106.06639  
**Usage:** The core asynchronous buffered aggregation architecture (AsyncBuffer with configurable K) is directly inspired by FedBuff. Updates are buffered per-task and aggregated when K updates accumulate.

---

## Coordinate-wise Trimmed Mean

**Citation:** Yin, D., Chen, Y., Kannan, R., and Bartlett, P.  
**Title:** "Byzantine-Robust Distributed Learning: Towards Optimal Statistical Rates"  
**Reference:** ICML 2018  
**URL:** https://arxiv.org/abs/1803.10032  
**Usage:** The coordinate-wise trimmed mean aggregation strategy in `aggregation/trimmed_mean.py` trims extreme values per coordinate across client updates before averaging, providing Byzantine fault tolerance.

---

## Differential Privacy (Moments Accountant, Simplified)

**Citation:** Abadi, M., Chu, A., Goodfellow, I., McMahan, H.B., Mironov, I., Talwar, K., and Zhang, L.  
**Title:** "Deep Learning with Differential Privacy"  
**Reference:** CCS 2016  
**URL:** https://arxiv.org/abs/1607.00133  
**Usage:** The PrivacyEngine in `privacy/dp.py` implements gradient clipping and Gaussian noise addition calibrated to the clipping norm. A simplified moments accountant tracks the cumulative privacy budget (epsilon, delta).
