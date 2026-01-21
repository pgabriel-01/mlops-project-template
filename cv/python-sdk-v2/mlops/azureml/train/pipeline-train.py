"""MLOps v2 Computer Vision Python SDK v2 training submission script."""
import os
import argparse

# Azure ML sdk v2 imports
from azure.identity import DefaultAzureCredential, InteractiveBrowserCredential
from azure.ai.ml import MLClient
from azure.ai.ml import command
from azure.ai.ml import Input, Output
from azure.ai.ml import dsl


def get_config_parser(parser: argparse.ArgumentParser = None):
    """Builds the argument parser for the script."""
    if parser is None:
        parser = argparse.ArgumentParser(description=__doc__)

    group = parser.add_argument_group("Azure ML references")
    group.add_argument(
        "--subscription_id",
        type=str,
        required=False,
        help="Subscription ID",
    )
    group.add_argument(
        "--resource_group",
        type=str,
        required=False,
        help="Resource group name",
    )
    group.add_argument(
        "--workspace_name",
        type=str,
        required=False,
        help="Workspace name",
    )
    group.add_argument(
        "-n",
        type=str,
        required=True,
        default="cv_image_classification_train",
        help="Experiment name",
    )
    parser.add_argument(
        "--wait",
        default=False,
        action="store_true",
        help="Wait for the job to finish",
    )

    group = parser.add_argument_group("Training parameters")
    group.add_argument(
        "--model_arch",
        type=str,
        default="resnet18",
        help="Model architecture (default: resnet18)",
    )
    group.add_argument(
        "--model_arch_pretrained",
        type=str,
        default="True",
        help="Use pretrained model (default: True)",
    )
    group.add_argument(
        "--num_epochs",
        type=int,
        default=10,
        help="Number of epochs to train (default: 10)",
    )
    group.add_argument(
        "--batch_size",
        type=int,
        default=64,
        help="Batch size for training (default: 64)",
    )
    group.add_argument(
        "--learning_rate",
        type=float,
        default=0.001,
        help="Learning rate (default: 0.001)",
    )
    group.add_argument(
        "--momentum",
        type=float,
        default=0.9,
        help="Momentum (default: 0.9)",
    )
    group.add_argument(
        "--model_registration_name",
        type=str,
        default="cv-image-classifier",
        help="Name to register model (default: cv-image-classifier)",
    )

    group = parser.add_argument_group("Data parameters")
    group.add_argument(
        "--train_data",
        type=str,
        required=True,
        help="Path/URI to training images",
    )
    group.add_argument(
        "--valid_data",
        type=str,
        required=True,
        help="Path/URI to validation images",
    )

    group = parser.add_argument_group("Compute parameters")
    group.add_argument(
        "--cpu_compute",
        type=str,
        default="cpu-cluster",
        help="CPU compute cluster name",
    )
    group.add_argument(
        "--gpu_compute",
        type=str,
        default="gpu-cluster",
        help="GPU compute cluster name",
    )
    group.add_argument(
        "--training_nodes",
        type=int,
        default=1,
        help="Number of nodes for distributed training",
    )
    group.add_argument(
        "--gpus_per_node",
        type=int,
        default=1,
        help="Number of GPUs per node",
    )

    return parser


def connect_to_aml(args):
    """Connect to Azure ML workspace using provided cli arguments."""
    try:
        credential = DefaultAzureCredential()
        # Check if given credential can get token successfully.
        credential.get_token("https://management.azure.com/.default")
    except Exception:
        # Fall back to InteractiveBrowserCredential in case DefaultAzureCredential not work
        credential = InteractiveBrowserCredential()

    # Get a handle to workspace
    try:
        # ml_client to connect using local config.json
        ml_client = MLClient.from_config(credential, path='config.json')

    except Exception:
        print(
            "Could not find config.json, using CLI args to connect to Azure ML workspace."
        )

        # tries to connect using cli args if provided
        ml_client = MLClient(
            subscription_id=args.subscription_id,
            resource_group_name=args.resource_group,
            workspace_name=args.workspace_name,
            credential=credential,
        )
    return ml_client


def build_components(args):
    """Builds the components for the pipeline."""
    DATA_SCIENCE_FOLDER = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "data-science", "src"
    )

    train_model = command(
        name="train_cv_model",
        display_name="Train CV Image Classification Model",
        inputs={
            "train_images": Input(type="uri_folder"),
            "valid_images": Input(type="uri_folder"),
            "model_arch": Input(type="string"),
            "model_arch_pretrained": Input(type="string"),
            "num_epochs": Input(type="integer"),
            "batch_size": Input(type="integer"),
            "learning_rate": Input(type="number"),
            "momentum": Input(type="number"),
            "register_model_as": Input(type="string", optional=True),
        },
        outputs=dict(
            model_output=Output(type="uri_folder", mode="rw_mount"),
            checkpoints=Output(type="uri_folder", mode="rw_mount"),
        ),
        code=DATA_SCIENCE_FOLDER,
        command="""python train.py \
                    --train_images ${{inputs.train_images}} \
                    --valid_images ${{inputs.valid_images}} \
                    --model_arch ${{inputs.model_arch}} \
                    --model_arch_pretrained ${{inputs.model_arch_pretrained}} \
                    --num_epochs ${{inputs.num_epochs}} \
                    --batch_size ${{inputs.batch_size}} \
                    --learning_rate ${{inputs.learning_rate}} \
                    --momentum ${{inputs.momentum}} \
                    --model_output ${{outputs.model_output}} \
                    --checkpoints ${{outputs.checkpoints}} \
                    $[[--register_model_as ${{inputs.register_model_as}}]] \
                """,
        environment="cv_image_classification_train@latest",
        distribution={
            "type": "PyTorch",
            # set process count to the number of gpus on the node
            "process_count_per_instance": args.gpus_per_node,
        },
        # set instance count to the number of nodes you want to use
        instance_count=args.training_nodes,
    )

    return {
        "train_model": train_model,
    }


def main():
    """Main entry point for the script."""
    parser = get_config_parser()
    args, _ = parser.parse_known_args()
    ml_client = connect_to_aml(args)

    # get components from build function
    components_dict = build_components(args)
    train_model = components_dict["train_model"]

    # build the pipeline using Azure ML SDK v2
    @dsl.pipeline(
        name="CV Training Pipeline",
        description="Computer Vision Image Classification Training Pipeline",
    )
    def cv_training_pipeline(
        train_images: Input(type="uri_folder"),
        valid_images: Input(type="uri_folder"),
        model_arch: str,
        model_arch_pretrained: str,
        num_epochs: int,
        batch_size: int,
        learning_rate: float,
        momentum: float,
        model_registration_name: str,
    ):
        train_model_step = train_model(
            train_images=train_images,
            valid_images=valid_images,
            model_arch=model_arch,
            model_arch_pretrained=model_arch_pretrained,
            num_epochs=num_epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
            momentum=momentum,
            register_model_as=model_registration_name,
        )
        train_model_step.compute = args.gpu_compute

        return {
            "trained_model": train_model_step.outputs.model_output,
            "training_checkpoints": train_model_step.outputs.checkpoints,
        }

    # instantiate the job
    pipeline_job = cv_training_pipeline(
        train_images=Input(type="uri_folder", path=args.train_data),
        valid_images=Input(type="uri_folder", path=args.valid_data),
        model_arch=args.model_arch,
        model_arch_pretrained=args.model_arch_pretrained,
        num_epochs=args.num_epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        momentum=args.momentum,
        model_registration_name=args.model_registration_name,
    )

    # submit the job
    print("Submitting the pipeline job to your AzureML workspace...")
    pipeline_job = ml_client.jobs.create_or_update(
        pipeline_job, experiment_name=args.n
    )

    print("The url to see your live job running is returned by the sdk:")
    print(pipeline_job.services["Studio"].endpoint)

    if args.wait:
        ml_client.jobs.stream(pipeline_job.name)


if __name__ == "__main__":
    main()
