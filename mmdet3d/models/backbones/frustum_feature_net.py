# Copyright (c) OpenMMLab. All rights reserved.
from collections import OrderedDict

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision
# import kornia

from mmdet.models import BACKBONES


@BACKBONES.register_module()
class FFN(nn.Module):

    def __init__(self, 
                constructor_name, 
                pretrained_path=None):
        """
        Initializes depth distribution network.
        Args:
            constructor [function]: Model constructor
            feat_extract_layer [string]: Layer to extract features from
            pretrained_path [string]: (Optional) Path of the model to load weights from
            aux_loss [bool]: Flag to include auxillary loss
        """
        super().__init__()
        
        self.pretrained_path = pretrained_path
        self.pretrained = pretrained_path is not None

        if self.pretrained:
            # Preprocess Module
            self.norm_mean = torch.Tensor([0.485, 0.456, 0.406])
            self.norm_std = torch.Tensor([0.229, 0.224, 0.225])

        # Model
        if constructor_name == "ResNet50":
            constructor = torchvision.models.segmentation.deeplabv3_resnet50
        elif constructor_name == "ResNet101":
            constructor = torchvision.models.segmentation.deeplabv3_resnet101
        else:
            raise NotImplementedError
        
        self.model = self.get_model(constructor=constructor)
        # self.feat_extract_layer = feat_extract_layer
        # self.model.return_layers = {
        #     feat_extract_layer: 'features',
        #     **self.model.backbone.return_layers
        # }

    def get_model(self, constructor):
        """
        Get model
        Args:
            constructor [function]: Model constructor
        Returns:
            model [nn.Module]: Model
        """
        # Get model
        model = constructor(pretrained=False, pretrained_backbone=True)

        # Update weights
        if self.pretrained_path is not None:
            model_dict = model.state_dict()

            # Get pretrained state dict
            pretrained_dict = torch.load(self.pretrained_path)
            pretrained_dict = self.filter_pretrained_dict(model_dict=model_dict, pretrained_dict=pretrained_dict)

            # Update current model state dict
            model_dict.update(pretrained_dict)
            model.load_state_dict(model_dict)
        
        my_model = nn.Sequential(
            model.backbone.conv1,
            model.backbone.bn1,
            model.backbone.relu,
            model.backbone.maxpool,
            model.backbone.layer1
        )

        return my_model

        # return model.backbone

    def filter_pretrained_dict(self, model_dict, pretrained_dict):
        """
        Removes layers from pretrained state dict that are not used or changed in model
        Args:
            model_dict [dict]: Default model state dictionary
            pretrained_dict [dict]: Pretrained model state dictionary
        Returns:
            pretrained_dict [dict]: Pretrained model state dictionary with removed weights
        """
        # Removes aux classifier weights if not used
        if "aux_classifier.0.weight" in pretrained_dict and "aux_classifier.0.weight" not in model_dict:
            pretrained_dict = {key: value for key, value in pretrained_dict.items()
                               if "aux_classifier" not in key}

        # Removes final conv layer from weights if number of classes are different
        model_num_classes = model_dict["classifier.4.weight"].shape[0]
        pretrained_num_classes = pretrained_dict["classifier.4.weight"].shape[0]
        if model_num_classes != pretrained_num_classes:
            pretrained_dict.pop("classifier.4.weight")
            pretrained_dict.pop("classifier.4.bias")

        return pretrained_dict

    def forward(self, images):
        """
        Forward pass
        Args:
            images [torch.Tensor(N, 3, H_in, W_in)]: Input images
        Returns
            result [dict[torch.Tensor]]: Depth distribution result
                feat [torch.Tensor(N, C, H_out, W_out)]: Image features
                out [torch.Tensor(N, num_classes, H_out, W_out)]: Classification logits
                aux [torch.Tensor(N, num_classes, H_out, W_out)]: Auxillary classification scores
        """
        # Preprocess images
        x = self.preprocess(images)

        # Extract features
        features = self.model(x)

        return features

    def preprocess(self, images):
        """
        Preprocess images
        Args:
            images [torch.Tensor(N, 3, H, W)]: Input images
        Return
            x [torch.Tensor(N, 3, H, W)]: Preprocessed images
        """
        x = images
        if self.pretrained:
            # Create a mask for padded pixels
            mask = torch.isnan(x)

            # Match ResNet pretrained preprocessing
            # x = kornia.normalize(x, mean=self.norm_mean, std=self.norm_std)

            # Make padded pixels = 0
            x[mask] = 0

        return x