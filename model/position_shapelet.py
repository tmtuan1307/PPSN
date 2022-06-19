import torch.nn as nn
import torch
import numpy
import torch.nn.functional as F

"""
------------------------------------------------------------------------------------------------------------------------
Original Learning TS Shapelets
------------------------------------------------------------------------------------------------------------------------
"""
class EuclidDistBlock(nn.Module):
    def __init__(self, shapelet, shapelet_info=None, len_ts=5, alpha=-10):
        super(PISDistBlock, self).__init__()
        self.alpha = alpha
        self.len_ts = len_ts
        sc = torch.FloatTensor(shapelet)
        self.shapelet = nn.Parameter(sc.view(1,sc.size(-1)))
        self.kernel_size = self.shapelet.size(-1)
        self.out_channels = len_ts - self.shapelet.size(-1) + 1
        self.false_conv_layer = nn.Conv1d(in_channels=2,
                                          out_channels=2,
                                          kernel_size=self.kernel_size,
                                          bias=False)
        data = torch.Tensor(numpy.eye(self.kernel_size))
        self.false_conv_layer.weight.data = data.view(self.kernel_size,
                                                      1,
                                                      self.kernel_size)
        for p in self.false_conv_layer.parameters():
            p.requires_grad = False

    def forward(self, x):
        reshaped_x1 = self.false_conv_layer(x)
        reshaped_x2 = torch.transpose(reshaped_x1, 1, 2)
        reshaped_x3 = reshaped_x2.contiguous().view(-1, self.kernel_size)
        dist1 = torch.sum(torch.square(reshaped_x3 - self.shapelet),1)/self.shapelet.size(-1)
        dist2 = dist1.view(x.size(0), 1, self.out_channels)

        # soft-minimum
        dist3 = self.soft_minimum(dist2)

        return dist3

    def soft_minimum(self, dist):
        temp = torch.exp(self.alpha * dist)
        return torch.sum(temp*dist, 2)/torch.sum(temp, 2)

    def hard_minimum(self, dist):
        min_dist, _ = torch.min(dist, 2)
        return min_dist

    def get_shapelets(self):
        return self.shapelet


class ShapeletLayer(nn.Module):
    def __init__(self, shapelets , len_ts):
        super(ShapeletLayer, self).__init__()
        self.blocks = nn.ModuleList([EuclidDistBlock(shapelet=shapelets[i],len_ts=len_ts)
                                     for i in range(len(shapelets))])

    def forward(self, x):
        out = torch.FloatTensor([]).to(x.device)
        for block in self.blocks:
            out = torch.cat((out, block(x)), dim=1)

        return out.view(out.size(0),1,out.size(1))

"""
------------------------------------------------------------------------------------------------------------------------
Perceptually and Position-aware Learning TS Shapelets
------------------------------------------------------------------------------------------------------------------------
"""
class PISDistBlock(nn.Module):
    """
    Parameter:
    shaplet:
    shaplet_info:
    in_chanels: input
    """
    def __init__(self, shapelet, shapelet_info=None, len_ts=5, alpha=-10,
                 window_size=10, norm=10, bounding_norm=100, maximum_ci=3):
        super(PISDistBlock, self).__init__()
        self.alpha = alpha
        self.norm = norm
        self.len_ts = len_ts
        self.window_size = window_size
        self.bounding_norm = bounding_norm
        self.max_norm_dist = nn.Parameter(torch.tensor(0.00001), requires_grad=False)
        self.maximum_ci = maximum_ci

        self.start_position = int(shapelet_info[1] - window_size)
        self.start_position = self.start_position if self.start_position >= 0 else 0
        self.end_position = int(shapelet_info[2] + window_size)
        self.end_position = self.end_position if self.end_position < len_ts else len_ts

        sc = torch.FloatTensor(shapelet)
        self.shapelet = nn.Parameter(sc.view(1,sc.size(-1)), requires_grad=True)
        self.kernel_size = self.shapelet.size(-1)
        self.out_channels = self.end_position - self.start_position - self.shapelet.size(-1) + 1
        self.false_conv_layer = nn.Conv1d(in_channels=2,
                                          out_channels=2,
                                          kernel_size=self.kernel_size,
                                          bias=False)
        data = torch.Tensor(numpy.eye(self.kernel_size))
        self.false_conv_layer.weight.data = data.view(self.kernel_size,
                                                      1,
                                                      self.kernel_size)

        self.false_conv_layer_ci = nn.Conv1d(in_channels=2,
                                          out_channels=2,
                                          kernel_size=self.kernel_size - 1,
                                          bias=False)
        data = torch.Tensor(numpy.eye(self.kernel_size - 1))
        self.false_conv_layer_ci.weight.data = data.view(self.kernel_size - 1,
                                                         1,
                                                         self.kernel_size - 1)

        for p in self.false_conv_layer.parameters():
            p.requires_grad = False
        for p in self.false_conv_layer_ci.parameters():
            p.requires_grad = False

    def forward(self, x, ep):
        self.ci_shapelet = torch.sum(torch.square(torch.subtract(self.shapelet.data.detach()[:,1:],
                                                                 self.shapelet.data.detach()[:,:-1]))) + (1/self.norm)

        pis = x[:,:,self.start_position:self.end_position]
        ci_pis = torch.square(torch.subtract(pis[:,:,1:], pis[:,:,:-1]))

        reshaped_pis1 = self.false_conv_layer(pis)
        reshaped_pis1 = torch.transpose(reshaped_pis1, 1, 2)
        reshaped_pis1 = reshaped_pis1.contiguous().view(-1, self.kernel_size)

        reshaped_ci_pis1 = self.false_conv_layer_ci(ci_pis)
        reshaped_ci_pis1 = torch.transpose(reshaped_ci_pis1, 1, 2)
        reshaped_ci_pis1 = reshaped_ci_pis1.contiguous().view(-1, self.kernel_size -1)
        reshaped_ci_pis1 = torch.sum(reshaped_ci_pis1, dim=1) + (1/self.norm)

        ci_shapelet_vec = self.ci_shapelet.repeat(reshaped_ci_pis1.size(0))
        max_ci = torch.max(reshaped_ci_pis1, ci_shapelet_vec)
        min_ci = torch.min(reshaped_ci_pis1, ci_shapelet_vec)
        ci_dist = max_ci / min_ci
        ci_dist[ci_dist > self.maximum_ci] = self.maximum_ci
        dist1 = torch.sum(torch.square(reshaped_pis1 - self.shapelet),1)
        dist1 = dist1 * ci_dist
        dist1 = dist1 / self.shapelet.size(-1)
        dist1 = dist1.view(x.size(0), 1, self.out_channels)

        # soft-minimum
        dist1 = self.soft_minimum(dist1)

        if ep == 0 and self.training:
            max_value = torch.max(dist1.detach())
            if max_value > self.max_norm_dist:
                self.max_norm_dist.data = max_value
        dist1 = 1 - dist1/self.max_norm_dist

        return dist1

    def soft_minimum(self, dist):
        dist1 = dist / self.bounding_norm
        temp = torch.exp(self.alpha * dist1)
        min_dist = torch.sum(temp*dist1, 2)/torch.sum(temp, 2)
        min_dist = min_dist * self.bounding_norm
        return min_dist

    def hard_minimum(self, dist):
        min_dist, _ = torch.min(dist, 2)
        return min_dist

    def get_shapelets(self):
        return self.shapelet


class PShapeletLayer(nn.Module):
    def __init__(self, shapelets_info, shapelets , len_ts, window_size=20, bounding_norm=100):
        super(PShapeletLayer, self).__init__()
        self.blocks = nn.ModuleList([
            PISDistBlock(shapelet=shapelets[i],shapelet_info=shapelets_info[i],len_ts=len_ts,window_size=window_size,
                         bounding_norm=bounding_norm)
            for i in range(len(shapelets))])

    def transform_to_complexity_invariance(self, x):
        return torch.square(torch.subtract(x[:, :, 1:], x[:, :, :-1]))

    def forward(self, x, ep):
        out = torch.FloatTensor([]).to(x.device)
        for block in self.blocks:
            out = torch.cat((out, block(x,ep=ep)), dim=1)

        return out.view(out.size(0),1,out.size(1))


class LearningPShapeletsModel(nn.Module):
    def __init__(self, shapelets_info, shapelets , len_ts, num_classes, sge=0, window_size=20, bounding_norm=100):
        super(LearningPShapeletsModel, self).__init__()
        self.sge = sge
        self.pshapelet_layer = PShapeletLayer(shapelets_info=shapelets_info, shapelets=shapelets,len_ts=len_ts,
                                              window_size=window_size,bounding_norm=bounding_norm)
        self.num_shapelets = len(shapelets)
        self.linear3 = nn.Linear(self.num_shapelets, num_classes)

    def forward(self, x, ep):
        y = self.pshapelet_layer(x,ep)
        y = torch.relu(y)
        if ep < self.sge:
            y = self.linear3(y.detach())
        else:
            y = self.linear3(y)
        y = torch.squeeze(y, 1)
        return y


if __name__ == '__main__':
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    # time_series = torch.Tensor([[[1., 2., 3., 4., 5.],[1., 1., 1., 1., 1.]], [[-4., -5., -6., -7., -8.],[-2., -2., -2., -2., -2.]]]).view(2,2,5)
    time_series = torch.Tensor([[1., 2., 3., 4., 5., 6., 7., 4., 5.], [-2., -2., -2., -2., -3., 4., 5., 4., 5.]]).view(2,1,9)
    shapelets = [[1., 2., 3.], [3., 4., 5.], [5., 6., 6.]]
    shapelets_info = numpy.array([[1., 1., 4., 4., 5.], [1., 1., 3., 4., 5.], [1., 2., 3., 4., 5.]])
    len_ts = time_series.size(-1)

    layer = PShapeletLayer(shapelets_info=shapelets_info, shapelets=shapelets,len_ts=len_ts, window_size=1).to("cuda:0")
    time_series = time_series.to(device)
    dists = layer.forward(time_series, ep=1)
    print(dists)