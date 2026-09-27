# Pilot-0 Baseline Ladder — M1.5 Report

Generated from frozen run manifests; split **Pilot-0 v1** was not modified. Labels: SILVER national map + WEAK local mask, **no GOLD**. Primary view `arbitrated_core`; `silver_strict` measures SILVER-product reproduction only. TEST was accessed exactly once after `FINAL_EVAL_LOCK.json` was frozen.

Spatial CI note: TEST contains 7 windows / 5 SILVER components, so spatial block-level confidence intervals are not estimable; the 3 seeds cover initialization/training randomness only, not geographic uncertainty.

## 1. Baseline main table

| Model | Variant | TEST core IoU | TEST core F1 | TEST core AUPRC |
|---|---|---:|---:|---:|
| SAI rule | spectral_sai | 0.181 | 0.306 | 0.181 |
| Random Forest | optical | 0.692 ± 0.006 | 0.818 ± 0.004 | 0.887 ± 0.004 |
| Random Forest | optical_indices | 0.691 ± 0.005 | 0.817 ± 0.004 | 0.898 ± 0.002 |
| Random Forest | optical_sar | 0.689 ± 0.001 | 0.816 ± 0.000 | 0.892 ± 0.003 |
| Random Forest | full | 0.691 ± 0.002 | 0.817 ± 0.001 | 0.901 ± 0.003 |
| U-Net | optical | 0.747 ± 0.075 | 0.854 ± 0.050 | 0.957 ± 0.006 |
| U-Net | optical_indices | 0.816 ± 0.035 | 0.899 ± 0.022 | 0.962 ± 0.011 |
| U-Net | optical_sar | 0.751 ± 0.055 | 0.857 ± 0.036 | 0.968 ± 0.009 |
| U-Net | full | 0.695 ± 0.109 | 0.817 ± 0.076 | 0.943 ± 0.033 |
| DeepLabV3+ | optical | 0.741 ± 0.037 | 0.851 ± 0.024 | 0.932 ± 0.014 |
| DeepLabV3+ | optical_indices | 0.749 ± 0.021 | 0.856 ± 0.014 | 0.939 ± 0.007 |
| DeepLabV3+ | optical_sar | 0.662 ± 0.073 | 0.795 ± 0.053 | 0.929 ± 0.010 |
| DeepLabV3+ | full | 0.703 ± 0.075 | 0.824 ± 0.052 | 0.914 ± 0.051 |
| SegFormer-B0 | optical | 0.206 ± 0.332 | 0.266 ± 0.413 | 0.416 ± 0.337 |
| SegFormer-B0 | optical_indices | 0.718 ± 0.066 | 0.835 ± 0.044 | 0.925 ± 0.026 |
| SegFormer-B0 | optical_sar | 0.415 ± 0.298 | 0.539 ± 0.338 | 0.726 ± 0.187 |
| SegFormer-B0 | full | 0.416 ± 0.336 | 0.524 ± 0.406 | 0.688 ± 0.392 |

## 2. Input ablation (Δ TEST core IoU vs optical)

| Model | optical Δ IoU | +indices Δ | +SAR Δ | full Δ |
|---|---:|---:|---:|---:|
| Random Forest | 0.000 | -0.001 | -0.003 | -0.001 |
| U-Net | 0.000 | 0.069 | 0.004 | -0.052 |
| DeepLabV3+ | 0.000 | 0.008 | -0.079 | -0.038 |
| SegFormer-B0 | 0.000 | 0.512 | 0.209 | 0.210 |

## 3. Seed-level results

| Model | Variant | Seed | core IoU | core F1 | strict IoU | strict F1 | thr |
|---|---|---|---:|---:|---:|---:|---:|
| DeepLabV3+ | full | 17 | 0.626 | 0.770 | 0.619 | 0.765 | 0.62 |
| DeepLabV3+ | full | 42 | 0.775 | 0.873 | 0.765 | 0.867 | 0.08 |
| DeepLabV3+ | full | 2026 | 0.710 | 0.830 | 0.702 | 0.825 | 0.15 |
| DeepLabV3+ | optical | 17 | 0.721 | 0.838 | 0.708 | 0.829 | 0.14 |
| DeepLabV3+ | optical | 42 | 0.784 | 0.879 | 0.770 | 0.870 | 0.26 |
| DeepLabV3+ | optical | 2026 | 0.719 | 0.836 | 0.706 | 0.828 | 0.06 |
| DeepLabV3+ | optical_indices | 17 | 0.766 | 0.867 | 0.756 | 0.861 | 0.15 |
| DeepLabV3+ | optical_indices | 42 | 0.726 | 0.841 | 0.717 | 0.835 | 0.34 |
| DeepLabV3+ | optical_indices | 2026 | 0.755 | 0.860 | 0.745 | 0.854 | 0.07 |
| DeepLabV3+ | optical_sar | 17 | 0.730 | 0.844 | 0.721 | 0.838 | 0.60 |
| DeepLabV3+ | optical_sar | 42 | 0.585 | 0.738 | 0.580 | 0.734 | 0.10 |
| DeepLabV3+ | optical_sar | 2026 | 0.672 | 0.804 | 0.665 | 0.799 | 0.05 |
| Random Forest | full | 17 | 0.693 | 0.818 | 0.683 | 0.812 | 0.05 |
| Random Forest | full | 42 | 0.691 | 0.817 | 0.682 | 0.811 | 0.05 |
| Random Forest | full | 2026 | 0.689 | 0.816 | 0.680 | 0.810 | 0.05 |
| Random Forest | optical | 17 | 0.698 | 0.822 | 0.685 | 0.813 | 0.05 |
| Random Forest | optical | 42 | 0.692 | 0.818 | 0.679 | 0.809 | 0.05 |
| Random Forest | optical | 2026 | 0.686 | 0.813 | 0.673 | 0.804 | 0.05 |
| Random Forest | optical_indices | 17 | 0.688 | 0.815 | 0.679 | 0.808 | 0.05 |
| Random Forest | optical_indices | 42 | 0.688 | 0.815 | 0.679 | 0.808 | 0.05 |
| Random Forest | optical_indices | 2026 | 0.696 | 0.821 | 0.687 | 0.814 | 0.05 |
| Random Forest | optical_sar | 17 | 0.688 | 0.815 | 0.680 | 0.809 | 0.05 |
| Random Forest | optical_sar | 42 | 0.689 | 0.816 | 0.680 | 0.809 | 0.05 |
| Random Forest | optical_sar | 2026 | 0.689 | 0.816 | 0.680 | 0.810 | 0.05 |
| SAI rule | spectral_sai | deterministic | 0.181 | 0.306 | 0.180 | 0.306 | 0.50 |
| SegFormer-B0 | full | 17 | 0.621 | 0.766 | 0.619 | 0.764 | 0.48 |
| SegFormer-B0 | full | 42 | 0.028 | 0.055 | 0.028 | 0.055 | 0.50 |
| SegFormer-B0 | full | 2026 | 0.599 | 0.749 | 0.592 | 0.744 | 0.60 |
| SegFormer-B0 | optical | 17 | 0.029 | 0.056 | 0.029 | 0.056 | 0.46 |
| SegFormer-B0 | optical | 42 | 0.000 | 0.000 | 0.000 | 0.000 | 0.58 |
| SegFormer-B0 | optical | 2026 | 0.589 | 0.741 | 0.578 | 0.733 | 0.07 |
| SegFormer-B0 | optical_indices | 17 | 0.793 | 0.884 | 0.783 | 0.878 | 0.14 |
| SegFormer-B0 | optical_indices | 42 | 0.667 | 0.800 | 0.659 | 0.795 | 0.22 |
| SegFormer-B0 | optical_indices | 2026 | 0.695 | 0.820 | 0.686 | 0.814 | 0.13 |
| SegFormer-B0 | optical_sar | 17 | 0.496 | 0.663 | 0.490 | 0.658 | 0.16 |
| SegFormer-B0 | optical_sar | 42 | 0.085 | 0.157 | 0.084 | 0.156 | 0.19 |
| SegFormer-B0 | optical_sar | 2026 | 0.664 | 0.798 | 0.655 | 0.791 | 0.38 |
| U-Net | full | 17 | 0.689 | 0.816 | 0.681 | 0.811 | 0.67 |
| U-Net | full | 42 | 0.807 | 0.893 | 0.796 | 0.887 | 0.25 |
| U-Net | full | 2026 | 0.589 | 0.741 | 0.584 | 0.737 | 0.65 |
| U-Net | optical | 17 | 0.782 | 0.878 | 0.767 | 0.868 | 0.81 |
| U-Net | optical | 42 | 0.799 | 0.888 | 0.783 | 0.878 | 0.07 |
| U-Net | optical | 2026 | 0.661 | 0.796 | 0.651 | 0.788 | 0.06 |
| U-Net | optical_indices | 17 | 0.842 | 0.914 | 0.830 | 0.907 | 0.07 |
| U-Net | optical_indices | 42 | 0.830 | 0.907 | 0.819 | 0.901 | 0.71 |
| U-Net | optical_indices | 2026 | 0.776 | 0.874 | 0.767 | 0.868 | 0.16 |
| U-Net | optical_sar | 17 | 0.741 | 0.851 | 0.733 | 0.846 | 0.36 |
| U-Net | optical_sar | 42 | 0.702 | 0.825 | 0.694 | 0.819 | 0.64 |
| U-Net | optical_sar | 2026 | 0.811 | 0.895 | 0.800 | 0.889 | 0.05 |

## 4. arbitrated_core vs silver_strict

| Model | Variant | core IoU | strict IoU | core Precision | strict Precision | core Recall | strict Recall |
|---|---|---:|---:|---:|---:|---:|---:|
| SAI rule | spectral_sai | 0.181 | 0.180 | 0.181 | 0.180 | 0.999 | 0.999 |
| Random Forest | optical | 0.692 ± 0.006 | 0.679 ± 0.006 | 0.840 ± 0.000 | 0.821 ± 0.000 | 0.797 ± 0.008 | 0.797 ± 0.008 |
| Random Forest | optical_indices | 0.691 ± 0.005 | 0.681 ± 0.005 | 0.853 ± 0.005 | 0.838 ± 0.004 | 0.784 ± 0.003 | 0.784 ± 0.003 |
| Random Forest | optical_sar | 0.689 ± 0.001 | 0.680 ± 0.000 | 0.878 ± 0.001 | 0.864 ± 0.001 | 0.762 ± 0.001 | 0.762 ± 0.001 |
| Random Forest | full | 0.691 ± 0.002 | 0.682 ± 0.002 | 0.874 ± 0.003 | 0.859 ± 0.003 | 0.767 ± 0.002 | 0.767 ± 0.002 |
| U-Net | optical | 0.747 ± 0.075 | 0.733 ± 0.072 | 0.788 ± 0.100 | 0.772 ± 0.096 | 0.941 ± 0.041 | 0.941 ± 0.041 |
| U-Net | optical_indices | 0.816 ± 0.035 | 0.805 ± 0.034 | 0.861 ± 0.057 | 0.849 ± 0.055 | 0.942 ± 0.024 | 0.942 ± 0.024 |
| U-Net | optical_sar | 0.751 ± 0.055 | 0.742 ± 0.054 | 0.766 ± 0.060 | 0.757 ± 0.058 | 0.976 ± 0.004 | 0.976 ± 0.004 |
| U-Net | full | 0.695 ± 0.109 | 0.687 ± 0.107 | 0.716 ± 0.127 | 0.708 ± 0.124 | 0.965 ± 0.019 | 0.965 ± 0.019 |
| DeepLabV3+ | optical | 0.741 ± 0.037 | 0.728 ± 0.036 | 0.797 ± 0.059 | 0.782 ± 0.057 | 0.915 ± 0.021 | 0.915 ± 0.021 |
| DeepLabV3+ | optical_indices | 0.749 ± 0.021 | 0.740 ± 0.020 | 0.800 ± 0.045 | 0.790 ± 0.043 | 0.924 ± 0.043 | 0.924 ± 0.043 |
| DeepLabV3+ | optical_sar | 0.662 ± 0.073 | 0.655 ± 0.071 | 0.679 ± 0.084 | 0.671 ± 0.082 | 0.967 ± 0.016 | 0.967 ± 0.016 |
| DeepLabV3+ | full | 0.703 ± 0.075 | 0.695 ± 0.073 | 0.745 ± 0.086 | 0.735 ± 0.084 | 0.928 ± 0.030 | 0.928 ± 0.030 |
| SegFormer-B0 | optical | 0.206 ± 0.332 | 0.202 ± 0.326 | 0.276 ± 0.392 | 0.270 ± 0.384 | 0.266 ± 0.427 | 0.266 ± 0.427 |
| SegFormer-B0 | optical_indices | 0.718 ± 0.066 | 0.709 ± 0.065 | 0.788 ± 0.055 | 0.777 ± 0.054 | 0.891 ± 0.066 | 0.891 ± 0.066 |
| SegFormer-B0 | optical_sar | 0.415 ± 0.298 | 0.410 ± 0.294 | 0.672 ± 0.215 | 0.656 ± 0.217 | 0.490 ± 0.345 | 0.490 ± 0.345 |
| SegFormer-B0 | full | 0.416 ± 0.336 | 0.413 ± 0.334 | 0.641 ± 0.465 | 0.634 ± 0.458 | 0.449 ± 0.359 | 0.449 ± 0.359 |

## 5. WEAK-only candidate response (diagnostic)

| Model | Variant | covered components | mean prob | median prob | above-thr fraction | component response rate |
|---|---|---:|---:|---:|---:|---:|
| DeepLabV3+ | full | 7 | 0.585 | 0.574 | 0.737 | 0.857 |
| DeepLabV3+ | optical | 7 | 0.477 | 0.454 | 0.740 | 0.810 |
| DeepLabV3+ | optical_indices | 7 | 0.591 | 0.595 | 0.743 | 0.810 |
| DeepLabV3+ | optical_sar | 7 | 0.707 | 0.728 | 0.873 | 0.905 |
| Random Forest | full | 7 | 0.112 | 0.080 | 0.244 | 0.286 |
| Random Forest | optical | 7 | 0.128 | 0.081 | 0.303 | 0.286 |
| Random Forest | optical_indices | 7 | 0.140 | 0.078 | 0.336 | 0.286 |
| Random Forest | optical_sar | 7 | 0.106 | 0.074 | 0.243 | 0.286 |
| SAI rule | spectral_sai | 7 | 1.000 | 1.000 | 1.000 | 1.000 |
| SegFormer-B0 | full | 7 | 0.449 | 0.446 | 0.286 | 0.238 |
| SegFormer-B0 | optical | 7 | 0.345 | 0.336 | 0.296 | 0.286 |
| SegFormer-B0 | optical_indices | 7 | 0.498 | 0.498 | 0.822 | 0.905 |
| SegFormer-B0 | optical_sar | 7 | 0.286 | 0.275 | 0.452 | 0.429 |
| U-Net | full | 7 | 0.688 | 0.698 | 0.710 | 0.714 |
| U-Net | optical | 7 | 0.595 | 0.601 | 0.636 | 0.714 |
| U-Net | optical_indices | 7 | 0.550 | 0.569 | 0.596 | 0.667 |
| U-Net | optical_sar | 7 | 0.616 | 0.644 | 0.671 | 0.810 |

_This is a candidate-response diagnostic, NOT accuracy or recall: there is no GOLD label for these pixels._

## 6. Missing-modality stress (full model, no retraining)

| Model | Input | core IoU | strict IoU | core F1 |
|---|---|---:|---:|---:|
| U-Net | full (no drop) | 0.695 ± 0.109 | 0.687 ± 0.107 | 0.817 ± 0.076 |
| U-Net | drop indices | 0.037 ± 0.017 | 0.037 ± 0.017 | 0.072 ± 0.032 |
| U-Net | drop sar | 0.660 ± 0.090 | 0.653 ± 0.088 | 0.793 ± 0.068 |
| U-Net | drop sar_indices | 0.127 ± 0.166 | 0.126 ± 0.164 | 0.202 ± 0.244 |
| DeepLabV3+ | full (no drop) | 0.703 ± 0.075 | 0.695 ± 0.073 | 0.824 ± 0.052 |
| DeepLabV3+ | drop indices | 0.307 ± 0.228 | 0.305 ± 0.226 | 0.437 ± 0.286 |
| DeepLabV3+ | drop sar | 0.621 ± 0.082 | 0.615 ± 0.080 | 0.764 ± 0.062 |
| DeepLabV3+ | drop sar_indices | 0.406 ± 0.124 | 0.406 ± 0.123 | 0.570 ± 0.129 |
| SegFormer-B0 | full (no drop) | 0.416 ± 0.336 | 0.413 ± 0.334 | 0.524 ± 0.406 |
| SegFormer-B0 | drop indices | 0.120 ± 0.111 | 0.119 ± 0.111 | 0.202 ± 0.181 |
| SegFormer-B0 | drop sar | 0.079 ± 0.108 | 0.078 ± 0.108 | 0.134 ± 0.177 |
| SegFormer-B0 | drop sar_indices | 0.001 ± 0.002 | 0.001 ± 0.002 | 0.002 ± 0.004 |

## 7. Calibration (15 equal-width ECE)

| Model | Variant | Brier | ECE(15) |
|---|---|---:|---:|
| SAI rule | spectral_sai | 0.819 | 0.819 |
| Random Forest | optical | 0.069 ± 0.000 | 0.081 ± 0.000 |
| Random Forest | optical_indices | 0.074 ± 0.000 | 0.085 ± 0.001 |
| Random Forest | optical_sar | 0.091 ± 0.000 | 0.109 ± 0.000 |
| Random Forest | full | 0.088 ± 0.001 | 0.106 ± 0.000 |
| U-Net | optical | 0.049 ± 0.032 | 0.081 ± 0.104 |
| U-Net | optical_indices | 0.029 ± 0.006 | 0.038 ± 0.031 |
| U-Net | optical_sar | 0.044 ± 0.024 | 0.052 ± 0.036 |
| U-Net | full | 0.078 ± 0.052 | 0.121 ± 0.108 |
| DeepLabV3+ | optical | 0.040 ± 0.008 | 0.025 ± 0.012 |
| DeepLabV3+ | optical_indices | 0.040 ± 0.007 | 0.027 ± 0.014 |
| DeepLabV3+ | optical_sar | 0.047 ± 0.007 | 0.039 ± 0.024 |
| DeepLabV3+ | full | 0.066 ± 0.048 | 0.091 ± 0.119 |
| SegFormer-B0 | optical | 0.148 ± 0.032 | 0.152 ± 0.032 |
| SegFormer-B0 | optical_indices | 0.049 ± 0.014 | 0.041 ± 0.008 |
| SegFormer-B0 | optical_sar | 0.107 ± 0.053 | 0.111 ± 0.042 |
| SegFormer-B0 | full | 0.094 ± 0.076 | 0.105 ± 0.068 |

## 8. Patch metrics (8-connectivity, one-to-one)

| Model | Variant | P@.25 | R@.25 | P@.50 | R@.50 | small-patch R |
|---|---|---:|---:|---:|---:|---:|
| SAI rule | spectral_sai | 0.800 | 0.333 | 0.800 | 0.333 | 0.500 |
| Random Forest | optical | 0.123 ± 0.005 | 0.694 ± 0.048 | 0.123 ± 0.005 | 0.694 ± 0.048 | 0.750 ± 0.000 |
| Random Forest | optical_indices | 0.128 ± 0.012 | 0.694 ± 0.048 | 0.118 ± 0.011 | 0.639 ± 0.048 | 0.750 ± 0.000 |
| Random Forest | optical_sar | 0.149 ± 0.014 | 0.667 ± 0.000 | 0.112 ± 0.010 | 0.500 ± 0.000 | 0.750 ± 0.000 |
| Random Forest | full | 0.136 ± 0.009 | 0.667 ± 0.000 | 0.108 ± 0.012 | 0.528 ± 0.048 | 0.750 ± 0.000 |
| U-Net | optical | 0.316 ± 0.073 | 0.556 ± 0.048 | 0.304 ± 0.087 | 0.528 ± 0.048 | 0.583 ± 0.144 |
| U-Net | optical_indices | 0.433 ± 0.194 | 0.611 ± 0.048 | 0.433 ± 0.194 | 0.611 ± 0.048 | 0.667 ± 0.144 |
| U-Net | optical_sar | 0.324 ± 0.049 | 0.528 ± 0.127 | 0.251 ± 0.029 | 0.417 ± 0.144 | 0.500 ± 0.000 |
| U-Net | full | 0.376 ± 0.074 | 0.556 ± 0.048 | 0.328 ± 0.118 | 0.472 ± 0.048 | 0.583 ± 0.144 |
| DeepLabV3+ | optical | 0.423 ± 0.053 | 0.611 ± 0.048 | 0.385 ± 0.061 | 0.556 ± 0.048 | 0.667 ± 0.144 |
| DeepLabV3+ | optical_indices | 0.404 ± 0.007 | 0.528 ± 0.048 | 0.365 ± 0.061 | 0.472 ± 0.048 | 0.500 ± 0.000 |
| DeepLabV3+ | optical_sar | 0.359 ± 0.088 | 0.500 ± 0.083 | 0.320 ± 0.114 | 0.444 ± 0.127 | 0.583 ± 0.144 |
| DeepLabV3+ | full | 0.456 ± 0.051 | 0.500 ± 0.144 | 0.354 ± 0.067 | 0.389 ± 0.127 | 0.500 ± 0.250 |
| SegFormer-B0 | optical | 0.146 ± 0.253 | 0.194 ± 0.337 | 0.104 ± 0.180 | 0.139 ± 0.241 | 0.250 ± 0.433 |
| SegFormer-B0 | optical_indices | 0.489 ± 0.056 | 0.556 ± 0.048 | 0.368 ± 0.134 | 0.417 ± 0.144 | 0.583 ± 0.144 |
| SegFormer-B0 | optical_sar | 0.428 ± 0.239 | 0.417 ± 0.220 | 0.367 ± 0.219 | 0.333 ± 0.167 | 0.417 ± 0.144 |
| SegFormer-B0 | full | 0.452 ± 0.431 | 0.278 ± 0.255 | 0.452 ± 0.431 | 0.278 ± 0.255 | 0.250 ± 0.250 |

## 9. Area error

| Model | Variant | abs area err (ha) | relative err | signed bias |
|---|---|---:|---:|---:|
| SAI rule | spectral_sai | 575.28 | 4.524 | 4.524 |
| Random Forest | optical | 6.48 ± 1.27 | 0.051 ± 0.010 | -0.051 ± 0.010 |
| Random Forest | optical_indices | 10.17 ± 0.48 | 0.080 ± 0.004 | -0.080 ± 0.004 |
| Random Forest | optical_sar | 16.92 ± 0.32 | 0.133 ± 0.003 | -0.133 ± 0.003 |
| Random Forest | full | 15.51 ± 0.51 | 0.122 ± 0.004 | -0.122 ± 0.004 |
| U-Net | optical | 27.06 ± 26.38 | 0.213 ± 0.207 | 0.213 ± 0.207 |
| U-Net | optical_indices | 12.57 ± 12.97 | 0.099 ± 0.102 | 0.099 ± 0.102 |
| U-Net | optical_sar | 35.52 ± 13.08 | 0.279 ± 0.103 | 0.279 ± 0.103 |
| U-Net | full | 48.15 ± 34.07 | 0.379 ± 0.268 | 0.379 ± 0.268 |
| DeepLabV3+ | optical | 19.47 ± 13.53 | 0.153 ± 0.106 | 0.153 ± 0.106 |
| DeepLabV3+ | optical_indices | 20.19 ± 14.41 | 0.159 ± 0.113 | 0.159 ± 0.113 |
| DeepLabV3+ | optical_sar | 56.16 ± 26.18 | 0.442 ± 0.206 | 0.442 ± 0.206 |
| DeepLabV3+ | full | 32.76 ± 18.75 | 0.258 ± 0.147 | 0.258 ± 0.147 |
| SegFormer-B0 | optical | 64.80 ± 53.40 | 0.510 ± 0.420 | -0.479 ± 0.470 |
| SegFormer-B0 | optical_indices | 17.13 ± 14.59 | 0.135 ± 0.115 | 0.135 ± 0.115 |
| SegFormer-B0 | optical_sar | 42.90 ± 50.68 | 0.337 ± 0.399 | -0.337 ± 0.399 |
| SegFormer-B0 | full | 51.18 ± 31.00 | 0.402 ± 0.244 | -0.402 ± 0.244 |

## 10. Efficiency

| Model | params | peak VRAM MiB | wall s | windows/s | checkpoint MiB | GPU |
|---|---:|---:|---:|---:|---:|---|
| SAI rule | N/A (CPU) | N/A | 0.6 | N/A | 0.00 | CPU |
| Random Forest | N/A (CPU) | N/A | 10.9 | N/A | 48.74 | CPU |
| U-Net | 14347025 | 319.1 | 47.8 | 110.8 | 54.82 | 2.0/4.0 |
| DeepLabV3+ | 12348113 | 290.4 | 40.2 | 109.5 | 47.20 | 2.0/4.0 |
| SegFormer-B0 | 3723809 | 229.9 | 66.4 | 93.9 | 14.26 | 2.0/4.0 |

## 11. Failure cases and notable observations

- Official runs FAILED: **0** of 49; retained early smoke failures: 2 (registry keeps both for traceability; they never entered the official matrix).
- VAL thresholds at the grid floor (0.05): 14 official runs (all Random Forest) — low probability scale under class imbalance; threshold protocol was not altered.
- TEST core IoU < 0.10 (seed-level collapse, reported as run, not averaged away):
  - SegFormer-B0 / full / seed 42: TEST core IoU 0.028
  - SegFormer-B0 / optical / seed 17: TEST core IoU 0.029
  - SegFormer-B0 / optical / seed 42: TEST core IoU 0.000
  - SegFormer-B0 / optical_sar / seed 42: TEST core IoU 0.085
- The first `final_eval.py` invocation aborted on the material WEAK-component guard (9 != 91) **before** any TEST metric was written; the candidate mask was corrected to the frozen Issue #4 definition (disagreement code 3, incl. IGNORE boundary buffer) and TEST was evaluated exactly once afterwards.
- TEST = 7 windows / 5 SILVER components: all differences at this scale are sensitive to individual patches; no spatial CI.

See `docs/experiments/registries/pilot0_registry.csv` for per-run checkpoint hashes, thresholds and GPU metadata.
